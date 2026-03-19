import os
import mibian
import math
# FILE: ts_nexus.py
import sys, os, asyncio, json, datetime, re, ssl, signal, time
import nexus_lock
nexus_lock.enforce_singleton()

# --- HEADLESS MODE CHECK ---
HEADLESS_MODE = "--headless" in sys.argv

try:
    import zmq, zmq.asyncio, aiohttp, requests
    import pytz 
    if not HEADLESS_MODE:
        from textual.app import App, ComposeResult
        from textual.widgets import DataTable, Static, Log
        from textual.containers import Vertical, Grid, Horizontal
        from rich.text import Text
except ImportError as e:
    # If headless, we don't need textual
    if HEADLESS_MODE and "textual" in str(e):
        pass
    else:
        print(f"CRITICAL: Missing dependency. {e}"); sys.exit(1)

# --- CONFIG ---
TS_CLIENT_ID = os.environ.get("TS_CLIENT_ID", "YOUR_TS_CLIENT_ID")
from nexus_config import (
    TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID, 
    ZMQ_PORT_MARKET, ZMQ_PORT_ACCOUNT, ZMQ_PORT_EXEC, ZMQ_PORT_CONTROL, 
    ZMQ_PORT_OPTION_TICK, ZMQ_PORT_BAR, ZMQ_PORT_LOGS,
    is_sleep_mode
)
YOUR_ACCOUNT_ID = TS_ACCOUNT_ID # Use TS_ACCOUNT_ID from config
ALL_SYMBOLS = ["SPY", "$SPX.X", "QQQ", "IWM", "$VIX.X", "@ES", "@NQ", "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLC", "XLI", "XLB", "XLRE", "XLU"]
BAR_SYMBOL = "SPY" 

# SAFETY
DRY_RUN_EXEC = False # Set to False for LIVE TRADING 

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path: sys.path.insert(0, script_dir)
try: from tradestation_explorer import TradeStationManager
except ImportError as e: print(f"CRITICAL: {e}"); sys.exit(1)

CHAIN_REGEX = re.compile(r"^(?P<ticker>[A-Z]+)\s*(?P<expiry>\d{6})(?P<type>[CP])(?P<strike_int>\d{5})(?P<strike_dec>\d{3})$")

def parse_occ_to_ts_symbol(occ_symbol: str) -> str:
    if not occ_symbol: return None
    clean_sym = occ_symbol.strip()
    match = CHAIN_REGEX.match(clean_sym)
    if match:
        d = match.groupdict()
        s = float(f"{int(d['strike_int'])}.{d['strike_dec']}")
        return f"{d['ticker']} {d['expiry']}{d['type']}{int(s) if s==int(s) else s}"
    return clean_sym

def get_dte_from_symbol(sym):
    # Parse "SPY 260116P710" -> 260116
    try:
        m = re.search(r'\s(\d{6})[CP]', sym)
        if m:
            d_str = m.group(1) # YYMMDD
            exp = datetime.datetime.strptime(d_str, "%y%m%d").replace(tzinfo=pytz.timezone('US/Eastern'))
            now = datetime.datetime.now(pytz.timezone('US/Eastern'))
            return (exp.date() - now.date()).days
    except: pass
    return 0

def antigravity_dump(filename, data_dictionary):
    """
    Atomically dumps data and prints a heartbeat log.
    """
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
        
        # NEW: Print a timestamp so the user sees it is alive
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"✅ [HEARTBEAT] Wrote {filename} at {current_time}")
        
    except Exception as e:
        print(f"❌ DUMP ERROR: {e}")

# --- CORE ENGINE (HEADLESS) ---
class NexusEngine:
    def __init__(self):
        self.zmq_ctx = zmq.asyncio.Context()
        self.TS = None
        self.current_option_stream = None
        self.latest_spy_price = 0.0
        self.oco_registry = {} # Risk Registry
        self.last_heartbeat = 0
        self.last_dump_time = 0
        self.last_dump_price = 0.0
        self.momentum_score = 0.0 # Initialize momentum score
        self.last_dump_price = 0.0
        self.momentum_score = 0.0 # Initialize momentum score
        self.positions = {} # Track positions for side determination
        self.load_active_targets() # Load existing state FIRST
        self.dump_active_targets() # Then dump (safe)

    def load_active_targets(self):
        """Loads the OCO registry from active_targets.json on startup."""
        try:
            if os.path.exists("active_targets.json"):
                with open("active_targets.json", "r") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.oco_registry = data
                        self.log_msg(f"Loaded {len(self.oco_registry)} active targets from disk.")
        except Exception as e:
            self.log_msg(f"Error loading active targets: {e}")

    def dump_active_targets(self):
        """Writes the current OCO registry to active_targets.json for Alert Manager."""
        try:
            with open("active_targets.json", "w") as f:
                json.dump(self.oco_registry, f, indent=2)
        except Exception as e:
            self.log_msg(f"Error dumping active targets: {e}")

    def _bind_socket(self, t, p): 
        s = self.zmq_ctx.socket(t); s.setsockopt(zmq.LINGER, 0); s.bind(f"tcp://*:{p}"); return s

    def file_log(self, msg):
        try:
            ts = datetime.datetime.now().strftime('%H:%M:%S')
            with open("nexus_engine.log", "a") as f: f.write(f"[{ts}] {msg}\n")
        except: pass

    def log_msg(self, m): 
        self.file_log(m) 
        try: t = datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')
        except: t = datetime.datetime.now().strftime('%H:%M:%S')
        full_msg = f"[{t}] {m}"
        print(full_msg) # Always print to stdout
        
        # Publish to Dashboard
        try: self.log_sock.send_multipart([b"LOG", full_msg.encode('utf-8')])
        except: pass

    def update_ui_status(self, t): pass # Override in UI
    def update_ui_table(self, sym, last=None, chg=None): pass # Override in UI

    async def start_workers(self):
        self.log_msg("--- SYSTEM START: NEXUS ENGINE (V2.5) ---")
        
        try:
            self.pub_socket = self._bind_socket(zmq.PUB, ZMQ_PORT_MARKET)
            self.account_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_ACCOUNT)
            self.exec_sock = self._bind_socket(zmq.REP, ZMQ_PORT_EXEC)
            self.option_tick_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_OPTION_TICK)
            self.bar_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_BAR)
            self.log_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_LOGS)
        except Exception as e: self.log_msg(f"BIND ERROR: {e} (Kill old process!)"); return

        if TradeStationManager:
            try: self.TS = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID); self.update_ui_status("● NEXUS V2.5 (ACTIVE)")
            except Exception as e: self.log_msg(f"AUTH FAIL: {e}")

        # Start Tasks
        tasks = [
            self.listen_for_orders(),
            self.start_main_stream(),
            self.listen_for_control(),
            self.stream_three_minute_bars(),
            self.heartbeat_monitor(),
            self.fetch_initial_price()
        ]
        if YOUR_ACCOUNT_ID and YOUR_ACCOUNT_ID != "FILL_ME_IN": 
            tasks.append(self.poll_account_data())
            
        await asyncio.gather(*tasks)

    async def fetch_initial_price(self):

        self.log_msg("Init: Fetching last known SPY price...")
        try:
            if not self.TS: return
            url = f"{self.TS.BASE_URL}/marketdata/quotes/SPY"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
            r = await asyncio.to_thread(requests.get, url, headers=headers)
            if r.status_code == 200:
                data = r.json()
                if "Quotes" in data and data["Quotes"]:
                    last = self._to_float(data["Quotes"][0].get('Last', 0))
                    if last > 0:
                        self.latest_spy_price = last
                        self.log_msg(f"Init: SPY Price set to ${last:.2f}")
                        self.check_risk_triggers(last) # Immediate Check
            else:
                self.log_msg(f"Init Price Fail: HTTP {r.status_code} {r.text}")
        except Exception as e: self.log_msg(f"Init Price Fail: {e}")

    async def heartbeat_monitor(self):
        while True:
            self.file_log(f"HEARTBEAT: SPY=${self.latest_spy_price:.2f} | Risk Rules: {len(self.oco_registry)}")
            
            # FORCE CHECK (For Off-Hours Testing)
            if self.latest_spy_price > 0:
                self.check_risk_triggers(self.latest_spy_price)
                
            await asyncio.sleep(5) 

    # --- RISK ENGINE LOGIC ---
    def is_valid_trigger_time(self):
        """
        Checks if current ET time is within valid trading hours for options execution.
        Window: 09:32:00 to 16:15:00 ET (Includes 2-min open delay).
        """
        try:
            now_et = datetime.datetime.now(pytz.timezone('US/Eastern'))
            t = now_et.time()
            
            # Start: 09:32 (2 min delay after 09:30 open)
            start_time = datetime.time(9, 32, 0)
            # End: 16:15 (SPY/SPX options trade until 4:15 PM ET)
            end_time = datetime.time(16, 15, 0)
            
            return start_time <= t <= end_time
            return start_time <= t <= end_time
        except Exception as e:
            self.log_msg(f"TIME CHECK ERROR: {e}. Defaulting to OPEN.")
            return True # Fail safe: Allow trading if check fails

    def check_risk_triggers(self, spy_price):
        if spy_price <= 0: return
        
        # MARKET HOURS CHECK
        if not self.is_valid_trigger_time():
            # Log suppression once per minute to avoid spam
            now_ts = time.time()
            if now_ts - getattr(self, "last_suppress_log", 0) > 60:
                t_now = datetime.datetime.now().strftime("%H:%M:%S")
                self.log_msg(f"RISK: Triggers Suspressed (Off-Hours/Delay). SPY={spy_price:.2f} LocalTime={t_now}")
                self.last_suppress_log = now_ts
            return

        now_ts = time.time()
        if now_ts - self.last_heartbeat > 10:
            self.last_heartbeat = now_ts
            if self.oco_registry:
                self.file_log(f"RISK CHECK: Scanning {len(self.oco_registry)} rules against SPY {spy_price}")

        triggered = []
        updates = []

        for sym, rule in self.oco_registry.items():
            if not rule.get('armed', False): continue
            
            stop = rule.get('stop', 0)
            targets = rule.get('targets', []) 
            take = rule.get('take', 0) 
            
            is_call = rule.get('type', 'C').upper().startswith('C')
            
            # 1. CHECK TARGETS (Partial Exits)
            for t in targets[:]:
                t_price = t.get('price', 0)
                t_qty = t.get('qty', 0)
                hit_t = False
                
                if is_call and spy_price >= t_price: hit_t = True
                elif not is_call and spy_price <= t_price: hit_t = True
                
                if hit_t:
                    reason = f"TARGET {spy_price} >= {t_price}" if is_call else f"TARGET {spy_price} <= {t_price}"
                    triggered.append((sym, t_qty, reason, None))
                    updates.append({'sym': sym, 'action': 'remove_target', 'target': t})
                    updates.append({'sym': sym, 'action': 'decrease_qty', 'qty': t_qty})

            # 2. CHECK STOP (Global)
            hit_s = False; reason_s = ""
            
            # SPREAD LOGIC
            if rule.get("type") == "SPREAD":
                trigger = rule.get("stop_trigger", 0)
                is_put = rule.get("is_put", False)
                # Bull Put: Lose if SPY drops. Stop if SPY <= Trigger.
                if is_put and spy_price <= trigger: hit_s = True; reason_s = f"SPREAD STOP {spy_price} <= {trigger}"
                # Bear Call: Lose if SPY rises. Stop if SPY >= Trigger.
                elif not is_put and spy_price >= trigger: hit_s = True; reason_s = f"SPREAD STOP {spy_price} >= {trigger}"
            
            # OPTION LOGIC
            elif is_call:
                if stop > 0 and spy_price <= stop: hit_s = True; reason_s = f"STOP {spy_price} <= {stop}"
            else:
                if stop > 0 and spy_price >= stop: hit_s = True; reason_s = f"STOP {spy_price} >= {stop}"
            
                if hit_s:
                    # [FIX] Pass the FULL RULE to triggered list so we don't rely on lookup after deletion
                    triggered.append((sym, rule['qty'], reason_s, rule)) 
                    updates.append({'sym': sym, 'action': 'delete_rule'})

        # Apply Updates
        for u in updates:
            s = u['sym']
            if s not in self.oco_registry: continue
            
            if u['action'] == 'remove_target':
                if 'targets' in self.oco_registry[s]:
                    try: self.oco_registry[s]['targets'].remove(u['target'])
                    except: pass
            elif u['action'] == 'decrease_qty':
                self.oco_registry[s]['qty'] -= u['qty']
                if self.oco_registry[s]['qty'] <= 0:
                    del self.oco_registry[s]
            elif u['action'] == 'delete_rule':
                if s in self.oco_registry: del self.oco_registry[s]
        
        if updates: self.dump_active_targets()

        # Execute Triggers
        for sym, qty, reason, rule_snapshot in triggered:
            if qty <= 0: continue
            self.log_msg(f"[bold red]TRIGGER FIRED: {sym} ({reason}) Qty:{qty}[/]")
            
            # Check if it's a SPREAD trigger (Using Snapshot)
            if rule_snapshot and rule_snapshot.get("type") == "SPREAD":
                asyncio.create_task(self.close_spread(rule_snapshot["short_sym"], rule_snapshot["long_sym"], rule_snapshot["qty"], rule_snapshot.get("side", "SELL")))
                continue
                
            dte = get_dte_from_symbol(sym)
            
            # Determine Side based on Position
            side = "SELL" # Default
            if sym in self.positions:
                q = self.positions[sym]
                if q < 0: side = "BUY" # Short Position -> Buy to Close
            
            loop = asyncio.get_running_loop()
            loop.create_task(self.smart_exit_routine(sym, qty, reason, dte, side=side))

    async def smart_exit_routine(self, symbol, qty, reason, dte, side="SELL"):
        """
        LIQUIDITY FORK EXECUTION LOGIC
        Path 1 (<14 DTE): Snap & Chase (Limit -> Market)
        Path 2 (>=14 DTE): Peg & Wait (Limit Chasing Upside)
        Path 3 (TAKE PROFIT): Aggressive Limit (Marketable Limit with Safety)
        """
        self.log_msg(f"EXEC: Smart Exit ({side}) for {symbol} (DTE:{dte}) Reason:{reason}")
        
        # [FIX] Map generic side to Explicit Closing Action
        # Options usually require "BuyClose" or "SellClose" to exit positions.
        # UPDATE: API requires "BuyToClose" / "SellToClose"
        if side == "BUY": side = "BuyToClose"
        elif side == "SELL": side = "SellToClose"
        
        # SCENARIO B: TAKE -> FORCE MARKET EXECUTION
        if "TAKE" in reason.upper() or "TARGET" in reason.upper():
            self.log_msg(f">> TARGET HIT: EXECUTING MARKET SELL (Force Fill)")
            await self.execute_order(symbol, qty, "MARKET", side)
            return

        is_liquid = dte < 14
        
        # --- PATH 1: SNAP & CHASE (Weeklies) ---
        if is_liquid:
            self.log_msg(f"EXEC: Path 1 (Snap & Chase) for {symbol}")
            mid_price = 0.0
            try:
                if self.TS:
                    q = await asyncio.to_thread(self.TS.get_quote_snapshot, symbol)
                    bid = float(q.get('Bid', 0)); ask = float(q.get('Ask', 0))
                    if bid > 0 and ask > 0: mid_price = round((bid + ask) / 2, 2)
                    else: mid_price = float(q.get('Last', 0))
            except: pass
            
            if mid_price == 0:
                self.log_msg("EXEC: No Quote, forcing MARKET")
                await self.execute_order(symbol, qty, "MARKET", side)
                return

            self.log_msg(f"EXEC: Submitting LIMIT {side} @ {mid_price}")
            # [MODIFIED] Force MARKET
            # oid = await self.execute_order(symbol, qty, "LIMIT", side, price=mid_price)
            oid = await self.execute_order(symbol, qty, "MARKET", side)
            
            await asyncio.sleep(5)
            
            self.log_msg("EXEC: Timeout. Cancelling and forcing MARKET.")
            if oid: await self.cancel_order(oid)
            await self.execute_order(symbol, qty, "MARKET", side)
            
        # --- PATH 2: PEG & WAIT (LEAPS) ---
        else:
            self.log_msg(f"EXEC: Path 2 (Peg & Wait) for {symbol}")
            self.log_msg("EXEC: Illiquid contract. Submitting LIMIT @ ASK/BID to avoid slippage.")
            try:
                if self.TS:
                    q = await asyncio.to_thread(self.TS.get_quote_snapshot, symbol)
                    ask = float(q.get('Ask', 0))
                    bid = float(q.get('Bid', 0))
                    
                    if side == "SELL":
                        price = ask if ask > 0 else float(q.get('Last', 0))
                    else: # BUY
                        price = bid if bid > 0 else float(q.get('Last', 0))
                        
                    # [MODIFIED] Force MARKET
                    # await self.execute_order(symbol, qty, "LIMIT", side, price=price)
                    await self.execute_order(symbol, qty, "MARKET", side)
            except:
                await self.execute_order(symbol, qty, "MARKET", side)

        async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False):
        """
        Fetches option chain.
        If raw=True: Returns list of individual options with Delta (Mibian).
        If raw=False: Returns list of Vertical Credit Spreads (Legacy).
        """
        self.log_msg(f"CHAIN: Fetching {ticker} chain (Target: {target_strike}, Raw: {raw})...")
        if not self.TS: return []

        try:
            # 1. Get Expirations
            url = f"{self.TS.BASE_URL}/marketdata/options/expirations/{ticker}"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
            r = await asyncio.to_thread(requests.get, url, headers=headers)
            if r.status_code != 200: 
                self.log_msg(f"DEBUG: Expirations API Failed: {r.status_code} {r.text}")
                return []
            
            expirations = r.json().get("Expirations", [])[:10] # Next 10 expiries
            
            results = []
            
            # 2. Get Current Spot Price (for Delta Calc)
            spot_price = 0.0
            try:
                q_spot = await asyncio.to_thread(self.TS.get_quote_snapshot, ticker)
                spot_price = float(q_spot.get("Last", 0))
            except: pass

            for exp in expirations:
                d_str = exp["Date"] # "2025-01-16T00:00:00Z"
                expiry_date = d_str.split("T")[0]
                exp_dt = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
                now_dt = datetime.datetime.now().date()
                dte = (exp_dt - now_dt).days
                if dte < 0: dte = 0
                
                # RAW MODE: Iterate Strikes around Target (For Debit/Custom Scans)
                if raw:
                    # Fetch reasonable range of strikes (e.g. +/- 10%)
                    center = float(target_strike) if target_strike else spot_price
                    if not center: center = 500 # Fallback
                    
                    # Fetch ALL strikes for expiry (Optimized: Filter locally)
                    url_s = f"{self.TS.BASE_URL}/marketdata/options/strikes/{ticker}?expiration={expiry_date}"
                    r_s = await asyncio.to_thread(requests.get, url_s, headers=headers)
                    strikes_data = r_s.json().get("Strikes", [])
                    
                    # Filter: +/- 75 points (Wider for SPY)
                    valid_strikes = []
                    for s_row in strikes_data:
                        try:
                            val = float(s_row[0])
                            if abs(val - center) < 75: 
                                valid_strikes.append(val)
                        except: pass
                        
                    # Build Symbols
                    symbols = []
                    exp_fmt = exp_dt.strftime("%y%m%d")
                    for s in valid_strikes:
                        s_str = f"{int(s)}" if s == int(s) else f"{s}"
                        if type_ == "CALL":
                            symbols.append(f"{ticker} {exp_fmt}C{s_str}")
                        elif type_ == "PUT":
                            symbols.append(f"{ticker} {exp_fmt}P{s_str}")
                    
                    # Batch Fetch Quotes (Chunking 20)
                    chunk_size = 20
                    for i in range(0, len(symbols), chunk_size):
                        chunk = symbols[i:i+chunk_size]
                        q_url = f"{self.TS.BASE_URL}/marketdata/quotes/{','.join(chunk)}"
                        r_q = await asyncio.to_thread(requests.get, q_url, headers=headers)
                        if r_q.status_code == 200:
                            quotes = r_q.json().get("Quotes", [])
                            for q in quotes:
                                try:
                                    sym = q["Symbol"]
                                    strike_part = sym.split(type_[0])[-1]
                                    strike_val = float(strike_part)
                                    
                                    bid = float(q.get("Bid", 0))
                                    ask = float(q.get("Ask", 0))
                                    
                                    # Calculate Delta (Mibian)
                                    iv = 20.0 
                                    delta = 0.0
                                    try:
                                        if spot_price > 0:
                                            # Interest ~ 4.5%
                                            c = mibian.BS([spot_price, strike_val, 4.5, dte], volatility=iv)
                                            if type_ == "CALL": delta = c.callDelta
                                            else: delta = c.putDelta
                                    except: pass
                                    
                                    results.append({
                                        "symbol": sym,
                                        "expiry": expiry_date,
                                        "dte": dte,
                                        "strike": strike_val,
                                        "type": type_,
                                        "bid": bid,
                                        "ask": ask,
                                        "delta": round(delta, 2)
                                    })
                                except Exception: pass
                                    
                # LEGACY MODE (Vertical Spreads - Credit Only)
                else: 
                    url_s = f"{self.TS.BASE_URL}/marketdata/options/strikes/{ticker}?expiration={expiry_date}"
                    r_s = await asyncio.to_thread(requests.get, url_s, headers=headers)
                    strikes = r_s.json().get("Strikes", [])
                    strikes = [float(s[0]) for s in strikes]
                    
                    short_strike = float(target_strike)
                    long_strike = short_strike - float(width) if type_ == "PUT" else short_strike + float(width)
                    
                    exp_fmt = exp_dt.strftime("%y%m%d")
                    def make_sym(s):
                        s_str = f"{int(s)}" if s == int(s) else f"{s}"
                        return f"{ticker} {exp_fmt}{type_[0]}{s_str}"

                    short_sym = make_sym(short_strike)
                    long_sym = make_sym(long_strike)
                    
                    quotes_url = f"{self.TS.BASE_URL}/marketdata/quotes/{short_sym},{long_sym}"
                    r_q = await asyncio.to_thread(requests.get, quotes_url, headers=headers)
                    if r_q.status_code == 200:
                        qs = r_q.json().get("Quotes", [])
                        q_short = next((q for q in qs if q["Symbol"] == short_sym), {})
                        q_long = next((q for q in qs if q["Symbol"] == long_sym), {})
                        
                        if q_short and q_long:
                            bid_short = float(q_short.get("Bid", 0))
                            ask_long = float(q_long.get("Ask", 0))
                            credit = bid_short - ask_long
                            risk = float(width) - credit
                            rr = (credit / risk) * 100 if risk > 0 else 0
                            breakeven = short_strike - credit if type_ == "PUT" else short_strike + credit
                            
                            results.append({
                                "expiry": expiry_date,
                                "dte": dte,
                                "short": short_strike,
                                "long": long_strike,
                                "credit": round(credit, 2),
                                "risk": round(risk, 2),
                                "rr": round(rr, 1),
                                "breakeven": round(breakeven, 2),
                                "short_sym": short_sym,
                                "long_sym": long_sym
                            })
            return results


    async def execute_spread(self, short_sym, long_sym, qty, price, stop_trigger, order_type="LIMIT", side="SELL"):
        """
        Executes a vertical spread.
        Side: "SELL" = Credit Spread (Sell Short, Buy Long). "BUY" = Debit Spread (Buy Short, Sell Long).
        """
        # [FIX] Ensure Symbol Formatting (Defensive)
        short_sym = parse_occ_to_ts_symbol(short_sym) or short_sym
        long_sym = parse_occ_to_ts_symbol(long_sym) or long_sym

        if DRY_RUN_EXEC:
            self.log_msg(f"DRY RUN: SPREAD {short_sym}/{long_sym} (Side: {side}, Stop: {stop_trigger})")
            return "DRY_OID"
            
        self.log_msg(f"LIVE SPREAD: {short_sym}/{long_sym} (Side: {side}, Stop: {stop_trigger})")
        try:
            if not self.TS: return None
            account_id = YOUR_ACCOUNT_ID
            
            # Construct Legs based on Side
            if side == "SELL":
                # Credit Spread: Sell the "Short" (Target), Buy the "Long" (Hedge)
                legs = [
                    {"Symbol": short_sym, "Quantity": str(qty), "TradeAction": "SellToOpen", "AssetType": "Option"},
                    {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "BuyToOpen", "AssetType": "Option"}
                ]
            else:
                # Debit Spread: Buy the "Short" (Target), Sell the "Long" (Hedge)
                legs = [
                    {"Symbol": short_sym, "Quantity": str(qty), "TradeAction": "BuyToOpen", "AssetType": "Option"},
                    {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "SellToClose", "AssetType": "Option"}
                ]
            
            # Profit Target Logic
            target_price = 0.0
            if side == "SELL":
                 target_price = round(float(price) * 0.5, 2) # Buy back cheap
            else:
                 target_price = round(float(price) * 1.5, 2) # Sell high
            
            # 1. Send Market Entry
            payload = {
                "AccountID": account_id,
                "OrderType": "Market" if order_type == "MARKET" else "Limit",
                "TimeInForce": {"Duration": "Day"},
                "Route": "Intelligent",
                "Legs": legs
            }
            
            if order_type != "MARKET":
                payload["LimitPrice"] = str(price)
            
            self.log_msg(f"DEBUG PAYLOAD (ENTRY): {json.dumps(payload)}")
            
            url = f"{self.TS.BASE_URL}/orderexecution/orders"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}", "Content-Type": "application/json"}
            
            entry_id = None
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, ssl=False) as resp:
                    resp_text = await resp.text()
                    if resp.status in [200, 201]:
                        data = json.loads(resp_text)
                        entry_id = data.get("Orders", [{}])[0].get("OrderID")
                        self.log_msg(f"ENTRY SENT: {entry_id}")
                    else:
                        self.log_msg(f"ENTRY FAIL: {resp_text}")
                        return None

            # 2. Send GTC Profit Target (Exit)
            if entry_id:
                # Construct Exit Legs (Reverse of Entry)
                if side == "SELL":
                    # Credit Exit: BuyToClose Short, SellToClose Long
                    exit_legs = [
                        {"Symbol": short_sym, "Quantity": str(qty), "TradeAction": "BuyToClose", "AssetType": "Option"},
                        {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "SellToClose", "AssetType": "Option"}
                    ]
                else:
                    # Debit Exit: SellToClose Short, BuyToClose Long
                    exit_legs = [
                        {"Symbol": short_sym, "Quantity": str(qty), "TradeAction": "SellToClose", "AssetType": "Option"},
                        {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "BuyToClose", "AssetType": "Option"}
                    ]

                exit_payload = {
                    "AccountID": account_id,
                    "OrderType": "Limit",
                    "LimitPrice": str(target_price),
                    "TimeInForce": {"Duration": "GTC"},
                    "Route": "Intelligent",
                    "Legs": exit_legs
                }
                self.log_msg(f"DEBUG PAYLOAD (EXIT): {json.dumps(exit_payload)}")
                
                # 2. Spawn Background Exit Monitor (Wait for Fill)
                asyncio.create_task(self.monitor_spread_exit(entry_id, exit_payload, short_sym, long_sym))
                self.log_msg(f"EXIT MANAGER STARTED for {entry_id}")

                # 3. Register Background Stop (Watchtower)
                is_put = "P" in short_sym
                is_bullish = (side == "SELL" and is_put) or (side == "BUY" and not is_put)
                
                self.oco_registry[short_sym] = {
                    "type": "SPREAD",
                    "short_sym": short_sym,
                    "long_sym": long_sym,
                    "qty": qty,
                    "stop_trigger": float(stop_trigger),
                    "armed": True,
                    "is_put": is_put,
                    "side": side,
                    "is_bullish": is_bullish
                }
                self.log_msg(f"STOP ARMED: {short_sym} @ SPY {stop_trigger}")
                self.dump_active_targets()
                
                return entry_id
            else:
                self.log_msg(f"SPREAD FAIL: {r.text}")
                return None

        except Exception as e:
            self.log_msg(f"SPREAD EXCEPTION: {e}")
            return None

    async def monitor_spread_exit(self, entry_id, exit_payload, short_sym, long_sym):
        """
        Polls the Entry Order ID. Once 'Filled', submits the GTC Exit order.
        Prevents 'Position Not Found' rejections.
        """
        self.log_msg(f"Waiting for Entry Fill: {entry_id}...")
        url_status = f"{self.TS.BASE_URL}/orderexecution/orders/{entry_id}"
        url_post = f"{self.TS.BASE_URL}/orderexecution/orders"
        headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}", "Content-Type": "application/json"}
        
        # [FIX] Increased timeout to 5 mins
        for i in range(300): 
            try:
                await asyncio.sleep(1)

                r = await asyncio.to_thread(requests.get, url_status, headers=headers)
                if r.status_code == 200:
                    d = r.json()
                    status = d.get("Status", "Unknown")
                    
                    if status == "Filled":
                        self.log_msg(f"ENTRY FILLED ({entry_id}). Submitting Exit...")
                        # Submit Exit with RETRY Logic
                        async with aiohttp.ClientSession() as session:
                             for attempt in range(3):
                                async with session.post(url_post, headers=headers, json=exit_payload, ssl=False) as resp:

                                    r_text = await resp.text()
                                    if resp.status in [200, 201]:
                                        data = json.loads(r_text)
                                        exit_id = data.get("Orders", [{}])[0].get("OrderID")
                                        self.log_msg(f"✅ GTC EXIT PLACED: {exit_id}")
                                        return
                                    else:
                                        self.log_msg(f"⚠️ EXIT ATTEMPT {attempt+1} FAIL: {r_text}")
                                        await asyncio.sleep(2) # Backoff
                        
                        self.log_msg(f"❌ EXIT PLACEMENT FAILED after retries.")
                        return
                    
                    elif status in ["Rejected", "Expired", "Canceled"]:
                        self.log_msg(f"⚠️ Entry {status}. Aborting Exit.")
                        return
                        
            except Exception as e:
                self.log_msg(f"Monitor Error: {e}")
                
        self.log_msg(f"⚠️ Monitoring Timeout for {entry_id}. Exit NOT placed.")

    async def close_spread(self, short_sym, long_sym, qty, side="SELL"):
        """
        Executes a Market Close for a spread (Panic Close).
        Side: "SELL" implies we OPENED by Selling (Credit), so we BUY TO CLOSE.
              "BUY" implies we OPENED by Buying (Debit), so we SELL TO CLOSE.
        """
        # [FIX] Sanitize Symbols
        short_sym = parse_occ_to_ts_symbol(short_sym) or short_sym
        long_sym = parse_occ_to_ts_symbol(long_sym) or long_sym
        
        self.log_msg(f"CLOSING SPREAD: {short_sym}/{long_sym} (Side: {side})")
        try:
            # Construct Legs based on Side (Reversing the Open)
            if side == "SELL":
                # Credit Open (Sell Short, Buy Long) -> Close: Buy Short, Sell Long
                legs = [
                    {"Symbol": short_sym, "Quantity": str(qty), "TradeAction": "BuyToClose", "AssetType": "Option"},
                    {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "SellToClose", "AssetType": "Option"}
                ]
            else:
                # Debit Open (Buy Short, Sell Long) -> Close: Sell Short, Buy Long
                legs = [
                    {"Symbol": short_sym, "Quantity": str(qty), "TradeAction": "SellToClose", "AssetType": "Option"},
                    {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "BuyToClose", "AssetType": "Option"}
                ]

            payload = {
                "AccountID": YOUR_ACCOUNT_ID,
                "OrderType": "Market",
                "TimeInForce": {"Duration": "Day"},
                "Route": "Intelligent",
                "Legs": legs
            }
            url = f"{self.TS.BASE_URL}/orderexecution/orders"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}", "Content-Type": "application/json"}
            await asyncio.to_thread(requests.post, url, json=payload, headers=headers)
        except Exception as e:
            self.log_msg(f"CLOSE FAIL: {e}")

    async def execute_order(self, symbol, qty, order_type, side, price=None):
        if DRY_RUN_EXEC:
            self.log_msg(f"DRY RUN: {side} {qty} {symbol} @ {order_type} {price if price else 'MKT'}")
            return "DRY_OID"
            
        self.log_msg(f"LIVE ORDER: {side} {qty} {symbol} @ {order_type}")
        try:
            if not self.TS: return None
            
            account_id = YOUR_ACCOUNT_ID
            if not account_id: return None
            
            # Determine TradeAction
            if side in ["BUY", "SELL"]:
                action = "Buy" if side == "BUY" else "Sell"
            else:
                action = side # Allow BuyToOpen, SellToClose, etc.

            # Determine AssetType (Crucial for Options)
            asset_type = "Stock"
            
            # [FIX] Robust Symbol Formatting for TradeStation V3
            # Standard: [Root] [YYMMDD][Type][Strike] (e.g. SPY 251219C680)
            # Input is likely OCC: SPY251219C00680000
            
            import re
            # Regex expects exactly 8 digits for strike in OCC format
            occ_match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", symbol)
            
            if occ_match:
                root = occ_match.group(1)
                date = occ_match.group(2)
                otype = occ_match.group(3)
                raw_strike = occ_match.group(4)
                
                # Convert Strike strings '00680000' -> 680
                try:
                    s_val = int(raw_strike) / 1000.0
                    s_str = f"{int(s_val)}" if s_val == int(s_val) else f"{s_val}"
                    
                    symbol = f"{root} {date}{otype}{s_str}"
                    asset_type = "Option"
                    self.log_msg(f"FMT: Converted OCC to TS -> {symbol}")
                except:
                    # Fallback if strike parse fails
                    symbol = f"{root} {date}{otype}{raw_strike}"
                    asset_type = "Option"
                    
            elif " " in symbol and any(c.isdigit() for c in symbol): 
                # Already specific format? e.g. 'SPY 251219C680'
                asset_type = "Option"
            
            # [CRITICAL PROTOCOL] Remap generic action for Options
            if asset_type == "Option":
                # Ensure valid TradeAction for options
                # Valid: BuyToOpen, BuyToClose, SellToOpen, SellToClose
                if action == "Buy": action = "BuyToOpen"
                elif action == "Sell": action = "SellToClose" 
                # If already specific (e.g. BuyToClose), keep it.

            payload = {
                "AccountID": account_id,
                "Symbol": symbol,
                "Quantity": str(qty),
                "OrderType": "Market" if order_type == "MARKET" else "Limit",
                "TradeAction": action,
                "AssetType": asset_type,
                "TimeInForce": {"Duration": "Day"},
                "Route": "Intelligent"
            }
            if price: payload["LimitPrice"] = str(price)
            
            self.log_msg(f"DEBUG PAYLOAD: {json.dumps(payload)}")
            
            url = f"{self.TS.BASE_URL}/orderexecution/orders"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}", "Content-Type": "application/json"}
            
            r = await asyncio.to_thread(requests.post, url, json=payload, headers=headers)
            if r.status_code in [200, 201]:
                d = r.json()
                oid = d.get("Orders", [{}])[0].get("OrderID")
                self.log_msg(f"ORDER SENT: {oid}")
                return oid
            else:
                self.log_msg(f"ORDER FAIL: {r.text}")
                return None
        except Exception as e:
            self.log_msg(f"ORDER EXCEPTION: {e}")
            return None

    async def cancel_order(self, oid):
        if DRY_RUN_EXEC: return
        try:
            url = f"{self.TS.BASE_URL}/orderexecution/orders/{oid}"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
            await asyncio.to_thread(requests.delete, url, headers=headers)
        except: pass

    async def start_main_stream(self):
        self.log_msg("Stream: Connecting...")
        while True:
            try:
                if not self.TS or not self.TS.access_token: await asyncio.sleep(5); continue
                url = f"{self.TS.BASE_URL}/marketdata/stream/quotes/{','.join(ALL_SYMBOLS)}"
                headers = {"Authorization": f"Bearer {self.TS.access_token}"}
                ssl_ctx = ssl.create_default_context(); ssl_ctx.check_hostname = False; ssl_ctx.verify_mode = ssl.CERT_NONE
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
                    async with s.get(url, headers=headers, timeout=None) as r:
                        if r.status == 200:
                            self.log_msg("Stream: ACTIVE")
                            async for line in r.content:
                                if line: await self.handle_tick(line)
                        else:
                            self.log_msg(f"Stream Error: {r.status}"); await asyncio.sleep(5)
            except Exception as e: self.log_msg(f"Stream Exception: {e}"); await asyncio.sleep(5)

    async def handle_tick(self, line):
        try:
            d = json.loads(line)
            if "Heartbeat" in d: return
            sym = d.get('Symbol','').strip(); 
            if not sym: return

            if sym == "SPY" and "Last" in d: 
                self.latest_spy_price = self._to_float(d['Last'])
                self.check_risk_triggers(self.latest_spy_price) # TRIGGER CHECK

                # --- ANTIGRAVITY STATE DUMP ---
                try:
                    now_ts = time.time()
                    last_price = self.latest_spy_price
                    
                    if abs(last_price - self.last_dump_price) > 0.01 or (now_ts - self.last_dump_time) > 1.0:
                        last_size = self._to_float(d.get('TradeVolume', d.get('Size', 0)))
                        
                        current_state = {
                            "last_price": last_price,
                            "tape_momentum_score": self.momentum_score,
                            "last_size": last_size,
                            "timestamp": time.time()
                        }
                        antigravity_dump("nexus_tape.json", current_state)
                        
                        self.last_dump_time = now_ts
                        self.last_dump_price = last_price
                except Exception as e: pass

            await self.pub_socket.send_multipart([sym.encode(), line])
            
            if sym in ALL_SYMBOLS:
                last = self._to_float(d.get('Last', 0)) if "Last" in d else None
                chg = self._to_float(d.get('NetChangePct', 0)) if "NetChangePct" in d else None
                self.update_ui_table(sym, last, chg)

        except: pass

    async def listen_for_orders(self):
        self.log_msg("Worker: Execution Gateway Active")
        while True:
            try:
                msg = await self.exec_sock.recv_json()
                self.file_log(f"CMD RECEIVED: {msg}")
                
                if not self.TS or not self.TS.access_token:
                    await self.exec_sock.send_json({"status": "error", "msg": "Auth Failed"}); continue

                cmd = msg.get("cmd", "").upper()
                token = self.TS._get_valid_access_token()
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                
                # --- ORDER MANAGEMENT ---
                if cmd == "GET_OPEN_ORDERS":
                    try:
                        url = f"https://api.tradestation.com/v3/brokerage/accounts/{YOUR_ACCOUNT_ID}/orders"
                        r = await asyncio.to_thread(requests.get, url, headers=headers)
                        if r.status_code == 200:
                            all_orders = r.json().get("Orders", [])
                            closed_states = ["FLL", "REJ", "CAN", "EXP", "CLS", "DON", "Filled", "Canceled", "Expired", "Rejected", "Closed", "Done"]
                            active = [o for o in all_orders if str(o.get("Status", "")).strip() not in closed_states]
                            await self.exec_sock.send_json({"status": "ok", "orders": active})
                        else: 
                            await self.exec_sock.send_json({"status": "error", "msg": f"API {r.status_code}"})
                    except Exception as e: 
                        await self.exec_sock.send_json({"status": "error", "msg": str(e)})
                    continue

                if cmd == "GET_MULTI_QUOTE":
                    try:
                        # Expects "symbols" (list of strings)
                        syms = msg.get("symbols", [])
                        if not syms:
                            await self.exec_sock.send_json({"status": "error", "msg": "No symbols"})
                            continue
                            
                        # TS API takes comma-separated list
                        sym_str = ",".join(syms)
                        url = f"https://api.tradestation.com/v3/marketdata/quotes/{sym_str}"
                        r = await asyncio.to_thread(requests.get, url, headers=headers)
                        
                        if r.status_code == 200:
                            quotes_list = r.json().get("Quotes", [])
                            # Return dict mapped by Symbol
                            # Note: TS returns Symbol in response, we map it back
                            q_map = {}
                            for q in quotes_list:
                                s = q.get("Symbol")
                                q_map[s] = {
                                    "Bid": float(q.get("Bid", 0)), 
                                    "Ask": float(q.get("Ask", 0)), 
                                    "Last": float(q.get("Last", 0))
                                }
                            await self.exec_sock.send_json({"status": "ok", "quotes": q_map})
                        else:
                            await self.exec_sock.send_json({"status": "error", "msg": f"API {r.status_code}"})
                    except Exception as e:
                        await self.exec_sock.send_json({"status": "error", "msg": str(e)})
                    continue

                if cmd == "CANCEL_ORDER":
                    oid = msg.get("order_id"); self.log_msg(f"REQ: CANCEL {oid}")
                    try:
                        url = f"https://api.tradestation.com/v3/orderexecution/orders/{oid}"
                        r = await asyncio.to_thread(requests.delete, url, headers=headers)
                        if r.status_code in [200, 201]: await self.exec_sock.send_json({"status": "ok", "msg": "Cancellation Sent"})
                        else: await self.exec_sock.send_json({"status": "error", "msg": r.json().get("Message", "Failed")})
                    except Exception as e: await self.exec_sock.send_json({"status": "error", "msg": str(e)})
                    continue

                # --- RISK MANAGEMENT (ARM/DISARM) ---
                sym = msg.get("symbol")
                qty = int(msg.get("qty", 1)) # Extract Qty EARLY for all commands

                if cmd == "ARM":
                    # qty is already extracted above
                    targets = msg.get("targets", []) 
                    
                    self.oco_registry[sym] = {
                        "stop": float(msg.get("stop", 0)),
                        "take": float(msg.get("take", 0)), 
                        "targets": targets,
                        "type": msg.get("type", "C"),
                        "qty": qty,
                        "armed": True
                    }
                    t_str = f"Targets: {len(targets)}" if targets else f"T:{msg.get('take')}"
                    self.log_msg(f"ARMED: {sym} [S:{msg.get('stop')} {t_str}]")
                    self.dump_active_targets()
                    await self.exec_sock.send_json({"status": "ok", "msg": "Armed"})
                    continue
                
                if cmd == "DISARM":
                    if sym in self.oco_registry: del self.oco_registry[sym]
                    self.log_msg(f"DISARMED: {sym}")
                    self.dump_active_targets()
                    await self.exec_sock.send_json({"status": "ok", "msg": "Disarmed"})
                    continue

                # --- EXECUTION ---
                # qty is already extracted above
                limit = msg.get("limit_price") or msg.get("price")
                if limit: limit = f"{float(limit):.2f}"
                
                # SMART EXIT INTERCEPT
                if cmd == "FORCE_EXIT":
                    reason = msg.get("reason", "UNKNOWN")
                    dte = msg.get("dte", 0)
                    side = msg.get("side", "SELL")
                    asyncio.create_task(self.smart_exit_routine(sym, qty, reason, dte, side=side))
                    await self.exec_sock.send_json({"status": "ok", "msg": "Smart Exit Started"})
                    continue

                # --- SPREAD SNIPER COMMANDS ---
                elif cmd == "GET_MANAGED_SPREADS":
                    # Return full registry values to allow UI to group legs
                    # Convert dict_values to list
                    spreads = list(self.oco_registry.values())
                    await self.exec_sock.send_json({"status": "ok", "spreads": spreads})
                    continue
                
                elif cmd == "GET_POSITIONS":
                    try:
                        positions = await asyncio.to_thread(self.TS.get_positions)
                        await self.exec_sock.send_json({"status": "ok", "positions": positions})
                    except Exception as e:
                        await self.exec_sock.send_json({"status": "error", "msg": str(e)})
                    continue

                elif cmd == "GET_CHAIN":
                    ticker = msg.get("ticker", "SPY")
                    strike = msg.get("strike")
                    width = msg.get("width")
                    type_ = msg.get("type", "PUT")
                    
                                        raw = msg.get('raw', False)
                    data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw)
                    await self.exec_sock.send_json({"status": "ok", "data": data})
                    continue

                if cmd == "EXECUTE_SPREAD":
                    short_sym = msg.get("short_sym")
                    long_sym = msg.get("long_sym")
                    qty = int(msg.get("qty", 1))
                    price = msg.get("price")
                    stop_trigger = msg.get("stop_trigger")
                    order_type = msg.get("order_type", "LIMIT")
                    side = msg.get("side", "SELL")
                    
                    oid = await self.execute_spread(short_sym, long_sym, qty, price, stop_trigger, order_type, side)
                    if oid:
                        await self.exec_sock.send_json({"status": "ok", "order_id": oid})
                    else:
                        await self.exec_sock.send_json({"status": "error", "msg": "Execution Failed"})
                    continue

                if cmd == "CLOSE_SPREAD":
                    short_sym = msg.get("short_sym")
                    long_sym = msg.get("long_sym")
                    qty = int(msg.get("qty", 1))
                    side = msg.get("side", "SELL") # Default logic is Credit Spread Close
                    asyncio.create_task(self.close_spread(short_sym, long_sym, qty, side))
                    await self.exec_sock.send_json({"status": "ok", "msg": "Close Sent"})
                    continue

                # GENERIC EXECUTE WRAPPER
                # We need to map the generic execute_order call to the specific API call logic
                # But wait, execute_order is defined in this class now.
                # However, execute_order takes (symbol, qty, order_type, side, price)
                # We need to map 'cmd' (BUY/SELL) to 'side'.
                # [MODIFIED] Force MARKET as requested by user
                # res = await self.execute_order(sym, qty, msg.get("type", "MARKET"), cmd, limit)
                res = await self.execute_order(sym, qty, "MARKET", cmd, None)
                
                if res and res.get("error"): await self.exec_sock.send_json({"status": "error", "msg": res["error"]})
                elif res: await self.exec_sock.send_json({"status": "ok", "id": res.get("id", "UNKNOWN"), "order_status": "SENT"})
                else: await self.exec_sock.send_json({"status": "error", "msg": "Unknown Error"})

            except Exception as e:
                self.log_msg(f"ERR: {e}"); 
                try: await self.exec_sock.send_json({"status": "error", "msg": str(e)})
                except: pass

    async def poll_account_data(self):
        while True:
            try:
                if is_sleep_mode():
                    await asyncio.sleep(60)
                    continue

                if self.TS:
                    balances = await asyncio.to_thread(self.TS.get_account_balances)
                    positions = await asyncio.to_thread(self.TS.get_positions)
                    
                    # Update Internal Position Map
                    self.positions = {}
                    for p in positions:
                        try:
                            s = p.get("Symbol")
                            q = int(p.get("Quantity", 0))
                            self.positions[s] = q
                        except: pass
                        
                    b = balances[0] if balances else {}
                    payload = {"total_account_value": self._to_float(b.get('Equity', 0)), "positions": positions}
                    await self.account_sock.send_multipart([b"A", json.dumps(payload).encode('utf-8')])
                    
                    # --- ACTIVE SPREAD MONITOR (50% PROFIT GUARD) ---
                    # Failsafe if GTC Order missed or disconnected
                    try:
                         # Build fast map
                         pos_map = {p.get("Symbol"): p for p in positions}
                         
                         for sym, rule in list(self.oco_registry.items()):
                             if rule.get("type") == "SPREAD" and rule.get("armed"):
                                 short_sym = rule.get("short_sym")
                                 long_sym = rule.get("long_sym")
                                 
                                 if short_sym in pos_map and long_sym in pos_map:
                                     p_short = pos_map[short_sym]
                                     p_long = pos_map[long_sym]
                                     
                                     # Calculate Net P/L
                                     pl_net = float(p_short.get("UnrealizedProfitLoss", 0)) + float(p_long.get("UnrealizedProfitLoss", 0))
                                     
                                     # Calculate Initial Credit (Basis estimate)
                                     val_net = float(p_short.get("MarketValue", 0)) + float(p_long.get("MarketValue", 0))
                                     cost_basis = val_net - pl_net
                                     
                                     # Only auto-close Credit Spreads (SELL Side)
                                     if rule.get("side") == "SELL":
                                         chk_basis = abs(cost_basis)
                                         if chk_basis > 0:
                                             pct = (pl_net / chk_basis) * 100
                                             if pct >= 50.0:
                                                 if self.is_valid_trigger_time():
                                                     self.log_msg(f"ð¸ [AUTO-PROFIT] {short_sym} spread is up {pct:.1f}%. Triggering Close!")
                                                     asyncio.create_task(self.close_spread(short_sym, long_sym, rule["qty"], "SELL"))
                                                     # Do not delete rule until filled? Or just set armed=True to prevent double fire?
                                                     # If we disarm, user is unprotected if close fails. 
                                                     # But if we don't, it might loop.
                                                     # Compromise: Set armed=False but log it clearly.
                                                     self.oco_registry[sym]["armed"] = False 
                                                     
                                                     # [NEW] Breakeven / Hard Stop Check (Fail-safe)
                                                     # If Price moves against us beyond breakeven, close.
                                                     # Breakeven = Short Strike - Credit (Put) or Short + Credit (Call)
                                                     if rule.get("auto_breakeven", True): # Enable by default for now
                                                         pass # Logic handled in check_risk_triggers if we update stop_trigger dynamically?
                                                         # For now, rely on strict Stop Trigger set at entry. 
                                                     self.dump_active_targets()
                                                 else:
                                                     # Log throttle (once per minute)
                                                     now_ts = time.time()
                                                     if now_ts - getattr(self, "last_ah_log", 0) > 60:
                                                         self.log_msg(f"⏸️ [AFTER HOURS] {short_sym} spread is up {pct:.1f}% (Target Met). Holding until open.")
                                                         self.last_ah_log = now_ts
                                     
                    except Exception as e:
                        print(f"Monitor Error: {e}")

            except: pass
            await asyncio.sleep(3)

    async def stream_three_minute_bars(self):
        while True:
            try:
                if is_sleep_mode():
                    await asyncio.sleep(60)
                    continue

                if not self.TS: await asyncio.sleep(5); continue
                url = f"{self.TS.BASE_URL}/marketdata/stream/barcharts/{BAR_SYMBOL}?interval=3&unit=Minute&barsback=10"
                headers = {"Authorization": f"Bearer {self.TS.access_token}"}
                ssl_ctx = ssl.create_default_context(); ssl_ctx.check_hostname=False; ssl_ctx.verify_mode=ssl.CERT_NONE
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
                    async with s.get(url, headers=headers, timeout=None) as r:
                        if r.status==200:
                            async for line in r.content:
                                if line: await self.bar_sock.send_multipart([b"BAR_3M", json.dumps(json.loads(line)).encode('utf-8')])
                        else: await asyncio.sleep(5)
            except: await asyncio.sleep(5)

    async def listen_for_control(self):
        sock = self.zmq_ctx.socket(zmq.SUB); sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_CONTROL}"); sock.subscribe(b"SUB")
        while True:
            try:
                _, symbol_bytes = await sock.recv_multipart(); symbol = symbol_bytes.decode('utf-8')
                if self.current_option_stream: self.current_option_stream.cancel()
                self.current_option_stream = asyncio.create_task(self.stream_one_option(symbol))
            except: pass

    async def stream_one_option(self, symbol):
        try:
            if is_sleep_mode(): return

            url = f"{self.TS.BASE_URL}/marketdata/stream/quotes/{symbol}"
            headers = {"Authorization": f"Bearer {self.TS.access_token}"}
            ssl_ctx = ssl.create_default_context(); ssl_ctx.check_hostname=False; ssl_ctx.verify_mode=ssl.CERT_NONE
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
                async with s.get(url, headers=headers, timeout=None) as r:
                    if r.status==200:
                        async for line in r.content:
                            if line:
                                try:
                                    d = json.loads(line); 
                                    if self.latest_spy_price > 0: d['UnderlyingPrice'] = self.latest_spy_price
                                    await self.option_tick_sock.send_multipart([b"OPTION_TICK", json.dumps(d).encode('utf-8')])
                                except: pass
        except: pass

    def _to_float(self, v):
        try: return float(v.replace(',','')) if isinstance(v,str) else float(v)
        except: return 0.0

# --- UI WRAPPER (CONDITIONAL) ---
if not HEADLESS_MODE:
    class TSNexusV25(App, NexusEngine):
        CSS = """
        Screen { background: #111; }
        #top_bar { dock: top; height: 3; background: #222; border-bottom: solid #0f0; padding: 0 1; }
        #status_bar { content-align: left middle; text-style: bold; width: 1fr; color: #0f0; }
        #mode_indicator { dock: right; width: 20; content-align: center middle; text-style: bold; }
        #main_grid { grid-size: 1; grid-columns: 100%; height: 1fr; }
        #left_pane { height: 100%; }
        #ticker_table { height: 4fr; background: #111; }
        Log { height: 1fr; border-top: solid #444; background: black; }
        """
        
        def __init__(self):
            App.__init__(self)
            NexusEngine.__init__(self)

        def compose(self) -> ComposeResult:
            with Horizontal(id="top_bar"): 
                yield Static("Initializing...", id="status_bar")
                yield Static("", id="mode_indicator")
            with Grid(id="main_grid"):
                with Vertical(id="left_pane"):
                    yield DataTable(id="ticker_table"); yield Log(id="event_log")

        def log_msg(self, m):
            # Call base logger (file + stdout)
            super().log_msg(m)
            # Add to UI Log
            try: 
                t = datetime.datetime.now().strftime('%H:%M:%S')
                self.query_one(Log).write(f"[{t}] {m}")
            except: pass

        def update_ui_status(self, t): 
            try: self.query_one("#status_bar", Static).update(Text.from_markup(t))
            except: pass

        def update_ui_table(self, sym, last=None, chg=None):
            try:
                dt = self.query_one("#ticker_table", DataTable)
                r = ALL_SYMBOLS.index(sym)
                if last is not None: dt.update_cell_at((r,1), f" {last:.2f} ")
                if chg is not None: dt.update_cell_at((r,2), Text(f" {chg:+.2f}% ", style="green" if chg>0 else "red"))
                dt.update_cell_at((r,3), f" {datetime.datetime.now().strftime('%H:%M:%S')} ")
            except: pass

        async def on_mount(self):
            # Set Mode Indicator
            mi = self.query_one("#mode_indicator", Static)
            if DRY_RUN_EXEC:
                mi.update("ð¢ DRY RUN")
                mi.styles.background = "#008000"; mi.styles.color = "white"
            else:
                mi.update("ð´ LIVE TRADING")
                mi.styles.background = "#D90429"; mi.styles.color = "white"

            dt = self.query_one("#ticker_table", DataTable)
            dt.add_columns(" SYMBOL ", " LAST ", " CHG % ", " TIME "); dt.cursor_type = "none"
            for s in ALL_SYMBOLS: dt.add_row(s, "-", "-", "-")

            # Start Engine Workers
            self.run_worker(self.start_workers)

# --- HEADLESS RUNNER ---
async def run_headless_engine():
    print("ðµ STARTING HEADLESS ENGINE...")
    engine = NexusEngine()
    await engine.start_workers()

# --- MAIN ---
if __name__ == "__main__": 
    if "--simulation" in sys.argv:
        print("ðµ TS NEXUS SIMULATION MODE ACTIVE")
        while True:
            try:
                price = 595.0 + (time.time() % 10) / 10.0 
                data = {
                    "last_price": price,
                    "tape_momentum_score": 5.0,
                    "last_size": 100,
                    "timestamp": time.time(),
                    "simulation": True
                }
                antigravity_dump("nexus_tape.json", data)
                time.sleep(1)
            except KeyboardInterrupt: break
    else:
        if HEADLESS_MODE:
            asyncio.run(run_headless_engine())
        else:
            TSNexusV25().run()