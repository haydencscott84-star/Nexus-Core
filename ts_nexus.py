import os
# FILE: ts_nexus.py
import sys, os, asyncio, json, datetime, re, ssl, signal, time, gc
from collections import deque
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
    ZMQ_PORT_OPTION_TICK, ZMQ_PORT_BAR, ZMQ_PORT_LOGS
)
YOUR_ACCOUNT_ID = TS_ACCOUNT_ID # Use TS_ACCOUNT_ID from config
ALL_SYMBOLS = ["SPY", "$SPX.X", "QQQ", "IWM", "$VIX.X", "@ES", "@NQ", "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLC", "XLI", "XLB", "XLRE", "XLU", "MESM26"]
BAR_SYMBOL = "SPY" 

# SAFETY
DRY_RUN_EXEC = False # Set to False for LIVE TRADING 

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path: sys.path.insert(0, script_dir)
try: from tradestation_explorer import TradeStationManager
except ImportError as e: print(f"CRITICAL: {e}"); sys.exit(1)

# [FIX] Import Execution Engine
try: from nexus_execution import NexusExecution
except ImportError as e: print(f"CRITICAL: Missing nexus_execution.py: {e}"); sys.exit(1)

CHAIN_REGEX = re.compile(r"^(?P<ticker>[A-Z]+)\s*(?P<expiry>\d{6})(?P<type>[CP])(?P<strike_int>\d{5})(?P<strike_dec>\d{3})$")

def parse_occ_to_ts_symbol(occ_symbol: str) -> str:
    """
    Normalizes option symbols. 
    TradeStation V3 API accepts BOTH full OCC and 'Simplified' formats for Order Execution.
    Refactored to PASS THROUGH simplified symbols (e.g. 'SPY 260206P680') which are valid,
    instead of forcing padding which causes 'INVALID SYMBOL' errors.
    """
    if not occ_symbol: return None
    clean_sym = occ_symbol.strip()
    
    # Check if already in full OCC format
    if CHAIN_REGEX.match(clean_sym):
        return clean_sym

    # Handle "Simplified" Format (e.g. SPY 260206P680)
    # Just verify it looks like a symbol, and return AS IS.
    simple_regex = re.compile(r"^(?P<ticker>[A-Z]+)\s*(?P<expiry>\d{6})(?P<type>[CP])(?P<strike>[\d\.]+)$")
    if simple_regex.match(clean_sym):
        return clean_sym
            
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
        self.tick_window = deque(maxlen=60) # Store last 60s of (time, price)
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
            log_file = "nexus_engine.log"
            # Strict Rotation: Check every log write? Expensive but safe.
            # Metatdata check is fast. Limit to 10MB instead of 50MB.
            if os.path.exists(log_file) and os.path.getsize(log_file) > 10 * 1024 * 1024:
                try:
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    os.rename(log_file, f"{log_file}.{timestamp}.bak")
                    # Cleanup old backups (keep last 3)
                    logs = sorted([f for f in os.listdir(".") if f.startswith("nexus_engine.log.")], reverse=True)
                    for old in logs[3:]: os.remove(old)
                except: pass

            ts = datetime.datetime.now().strftime('%H:%M:%S')
            with open(log_file, "a") as f: f.write(f"[{ts}] {msg}\n")
        except: pass

    def log_msg(self, m): 
        self.file_log(m) 
        # try: t = datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')
        # except: t = datetime.datetime.now().strftime('%H:%M:%S')
        # full_msg = f"[{t}] {m}"
        # print(full_msg) # Always print to stdout
        
        # [OPT] Only print critical/info messages to stdout to save buffer
        if "DEBUG" not in m and "TRACE" not in m and "Stream" not in m:
             try: t = datetime.datetime.now(pytz.timezone('US/Eastern')).strftime('%H:%M:%S')
             except: t = datetime.datetime.now().strftime('%H:%M:%S')
             print(f"[{t}] {m}")

        try: 
            # Throttle ZMQ Payload (Only send important logs to dashboard)
            if "DEBUG" not in m:
                t = datetime.datetime.now().strftime('%H:%M:%S')
                self.log_sock.send_multipart([b"LOG", f"[{t}] {m}".encode('utf-8')])
        except: pass

    def update_ui_status(self, t): pass # Override in UI
    def update_ui_table(self, sym, last=None, chg=None): pass # Override in UI

    async def start_workers(self):
        self.log_msg("--- SYSTEM START: NEXUS ENGINE (V2.5) ---")
        
        try:
            self.pub_socket = self._bind_socket(zmq.PUB, ZMQ_PORT_MARKET)
            self.account_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_ACCOUNT)
            self.exec_sock = self._bind_socket(zmq.ROUTER, ZMQ_PORT_EXEC)
            self.option_tick_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_OPTION_TICK)
            self.bar_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_BAR)
            self.log_sock = self._bind_socket(zmq.PUB, ZMQ_PORT_LOGS)
        except Exception as e: self.log_msg(f"BIND ERROR: {e} (Kill old process!)"); return

        if TradeStationManager:
            try: 
                self.log_msg("AUTH: Initializing TradeStationManager...")
                self.TS = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID)
                self.log_msg("AUTH: Success! TradeStationManager Ready.")
                self.update_ui_status("● NEXUS V2.5 (ACTIVE)")
            except Exception as e: self.log_msg(f"AUTH FAIL: {e}")

        # Start Tasks
        tasks = [
            self.listen_for_orders(),
            self.start_main_stream(),
            self.listen_for_control(),
            self.stream_three_minute_bars(),
            self.heartbeat_monitor(),
            self.fetch_initial_price(),
            self.account_heartbeat() # [NEW] Pulse
        ]
        if YOUR_ACCOUNT_ID and YOUR_ACCOUNT_ID != "FILL_ME_IN": 
            tasks.append(self.stream_account_positions())
            tasks.append(self.poll_account_positions()) # [NEW] Robust Poller
            
        await asyncio.gather(*tasks)

    async def account_heartbeat(self):
        """Ensures Account Data is broadcast every 5s even if Stream is silent."""
        self.log_msg("Init: Account Heartbeat Active (5s)")
        while True:
            try:
                # 1. Use Cached Payload if available
                if hasattr(self, 'last_acct_payload') and self.last_acct_payload:
                    await self.account_sock.send_multipart([b"A", json.dumps(self.last_acct_payload).encode('utf-8')])
                else:
                    # 2. Force Sync Fetch if Empty (Boot)
                    if self.TS:
                        try:
                            # 1. Main Account
                            b = await asyncio.to_thread(self.TS.get_account_balances)
                            p = await asyncio.to_thread(self.TS.get_positions)
                            bal = b[0] if b else {}
                            equity_main = self._to_float(bal.get('Equity', 0))
                            ytd_main = equity_main - 52648.47
                            
                            # 2. Futures Account
                            bal_fut_list = await asyncio.to_thread(self.TS.get_account_balances, "210VGM01")
                            bal_fut = bal_fut_list[0] if bal_fut_list else {}
                            equity_fut = self._to_float(bal_fut.get('Equity', 0))
                            
                            # [FIX] Merge Positions First for Accurate PNL Calc
                            pos_fut = await asyncio.to_thread(self.TS.get_positions, "210VGM01")
                            all_positions = list(p)
                            if pos_fut: all_positions.extend(pos_fut)
                            
                            # 3. Aggregate
                            agg_equity = equity_main + equity_fut
                            # [FIX] Calculate Unrealized PNL from POSITIONS (Balance endpoint unreliable)
                            agg_unrealized = sum(self._to_float(pos.get('UnrealizedProfitLoss', 0)) for pos in all_positions)
                            agg_realized = self._to_float(bal.get('RealizedProfitLoss', 0)) + self._to_float(bal_fut.get('RealizedProfitLoss', 0))
                            
                            # [FIX] Global YTD Calculation (Grand Total Start: $52,648.47)
                            agg_ytd = agg_equity - 52648.47
                            
                            todays_main = self._to_float(bal.get('TodaysProfitLoss', 0))
                            todays_fut = self._to_float(bal_fut.get('TodaysProfitLoss', 0))
                            agg_todays = todays_main + todays_fut
                            
                            agg_bp = self._to_float(bal.get('BuyingPower', 0)) + self._to_float(bal_fut.get('BuyingPower', 0))
                            agg_exp = (self._to_float(bal.get('MktValue', 0)) if bal.get('MktValue') else self._to_float(bal.get('MarketValue', 0))) + \
                                      (self._to_float(bal_fut.get('MktValue', 0)) if bal_fut.get('MktValue') else self._to_float(bal_fut.get('MarketValue', 0)))

                            payload = {
                                "total_account_value": agg_equity,
                                "unrealized_pnl": agg_unrealized,
                                "realized_pnl": agg_realized,
                                "ytd_pnl": agg_ytd,
                                "todays_pnl": agg_todays,
                                "buying_power": agg_bp,
                                "value_of_open_positions": agg_exp,
                                "positions": all_positions
                            }

                        except Exception as e:
                            self.log_msg(f"HEARTBEAT AGG ERROR: {e}")
                            # Fallback
                            b = await asyncio.to_thread(self.TS.get_account_balances)
                            p = await asyncio.to_thread(self.TS.get_positions)
                            bal = b[0] if b else {}
                            payload = {
                                "total_account_value": self._to_float(bal.get('Equity', 0)),
                                "unrealized_pnl": self._to_float(bal.get('UnrealizedProfitLoss', 0)),
                                "positions": p
                            }

                        self.last_acct_payload = payload
                        await self.account_sock.send_multipart([b"A", json.dumps(payload).encode('utf-8')])
                        
                        # [FIX] Dump active_portfolio.json for nexus_greeks.py
                        antigravity_dump("active_portfolio.json", payload)
                        self.log_msg("Heartbeat: Forced Initial Sync & Dumped Portfolio")
            except Exception as e:
                self.log_msg(f"Heartbeat pulse err: {e}")
                import traceback
                self.log_msg(traceback.format_exc())
                pass
            await asyncio.sleep(5)


    async def fetch_initial_price(self):
        self.log_msg("Init: Fetching last known SPY price...")
        try:
             url = f"{self.TS.BASE_URL}/marketdata/quotes/SPY"
             headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
             import requests
             r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=5)
             if r.status_code == 200:
                 q = r.json().get("Quotes", [])
                 if q:
                     price = float(q[0].get("Last", 0))
                     self.latest_spy_price = price
                     self.log_msg(f"Init: SPY Price set to {price}")
                     # Force Broadcast
                     if hasattr(self, 'pub_socket'):
                         await self.pub_socket.send_multipart([b"SPY", json.dumps({"Symbol":"SPY", "Last":price}).encode('utf-8')])
        except Exception as e:
            self.log_msg(f"Init Error: {e}")
        # try:
        #     if not self.TS: return
        #     url = f"{self.TS.BASE_URL}/marketdata/quotes/SPY"
        #     headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
        #     # [FIX] Added timeout to prevent infinite hang on startup
        #     r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
        #     if r.status_code == 200:
        #         data = r.json()
        #         if "Quotes" in data and data["Quotes"]:
        #             last = self._to_float(data["Quotes"][0].get('Last', 0))
        #             if last > 0:
        #                 self.latest_spy_price = last
        #                 self.log_msg(f"Init: SPY Price set to ${last:.2f}")
        #                 self.check_risk_triggers(last) # Immediate Check
        #     else:
        #         self.log_msg(f"Init Price Fail: HTTP {r.status_code} {r.text}")
        # except Exception as e: self.log_msg(f"Init Price Fail: {e}")

    async def heartbeat_monitor(self):
        while True:
            # MEMORY MANAGEMENT (Agghresive Pruning)
            self.prune_memory()
            gc.collect()

            self.file_log(f"HEARTBEAT: SPY=${self.latest_spy_price:.2f} | Risk Rules: {len(self.oco_registry)} | RAM: GC OK")
            
            # FORCE CHECK AND BROADCAST (For Off-Hours)
            if self.latest_spy_price > 0:
                self.check_risk_triggers(self.latest_spy_price)
                if hasattr(self, 'pub_socket'):
                    # Broadcast Heartbeat so Dashboard sees price
                    await self.pub_socket.send_multipart([b"SPY", json.dumps({"Symbol":"SPY", "Last":self.latest_spy_price}).encode('utf-8')])
                
            await asyncio.sleep(5) 

    def prune_memory(self):
        """Aggressively clears caches and temp lists to prevent leaks."""
        try:
            now_ts = time.time()
            
            # 1. Prune Position Cache (> 60s old)
            if hasattr(self, "_pos_cache"):
                keys_to_del = [k for k, v in self._pos_cache.items() if now_ts - v[0] > 60]
                for k in keys_to_del: del self._pos_cache[k]
            
            # 2. Prune Tick Window (Backup check)
            if hasattr(self, "tick_window"):
                while len(self.tick_window) > 100: # Safety Cap
                    self.tick_window.popleft()
            
            # 3. Clear Request Cache (if any implicit ones exist)
            # (aiohttp sessions are context-managed, so they clean up automatically)
            
        except Exception as e:
            self.file_log(f"Prune Error: {e}")

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

    
    async def fetch_orats_ivr(self, ticker):
        """Fetches IV (30d) and IV Rank (1y Percentile) from ORATS."""
        try:
            from nexus_config import ORATS_API_KEY
            if not ORATS_API_KEY: return 0.0, 0.0
            
            url = "https://api.orats.io/datav2/ivrank"
            params = {"token": ORATS_API_KEY, "ticker": ticker}
            
            # Use requests in thread to avoid blocking
            import requests
            r = await asyncio.to_thread(requests.get, url, params=params, timeout=10)
            
            if r.status_code == 200:
                d = r.json()
                data = d.get("data", [])
                if data:
                    core = data[0]
                    iv = float(core.get('iv', 0))
                    ivr = float(core.get('ivPct1y', 0))
                    self.log_msg(f"ORATS: {ticker} IV={iv}% IVR={ivr}")
                    return iv, ivr
            return 0.0, 0.0
            
        except Exception as e:
            self.log_msg(f"ORATS Error: {e}")
            return 0.0, 0.0

    async def fetch_option_chain(self, ticker, target_strike, width, type_):
        """
        Fetches option chain for the next 20 expirations in PARALLEL.
        Optimized: Removes redundant 'get strikes' call. Constructs symbols directly.
        """
        self.log_msg(f"CHAIN: Fetching {ticker} chain near {target_strike}...")
        if not self.TS: return []

        try:
            # 1. Get Expirations
            url = f"{self.TS.BASE_URL}/marketdata/options/expirations/{ticker}"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
            r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            if r.status_code != 200: 
                self.log_msg(f"DEBUG: Expirations API Failed: {r.status_code} {r.text}")
                return []
            
            expirations = r.json().get("Expirations", [])[:20] # Next 20
            
            async def process_expiration(exp):
                try:
                    d_str = exp["Date"]
                    expiry_date = d_str.split("T")[0]
                    exp_dt = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
                    now_dt = datetime.datetime.now().date()
                    dte = (exp_dt - now_dt).days
                    
                    exp_fmt = exp_dt.strftime("%y%m%d")
                    
                    def make_sym(s):
                        s_str = f"{int(s)}" if s == int(s) else f"{s}"
                        return f"{ticker} {exp_fmt}{type_[0]}{s_str}"

                    # Logic: Short is Target. Long is Target +/- Width
                    short_strike = float(target_strike)
                    long_strike = short_strike - float(width) if type_ == "PUT" else short_strike + float(width)

                    short_sym = make_sym(short_strike)
                    long_sym = make_sym(long_strike)
                    
                    # Fetch Quotes (Async thread)
                    quotes_url = f"{self.TS.BASE_URL}/marketdata/quotes/{short_sym},{long_sym}"
                    r_q = await asyncio.to_thread(requests.get, quotes_url, headers=headers, timeout=10)
                    if r_q.status_code == 200:
                        qs = r_q.json().get("Quotes", [])
                        q_short = next((q for q in qs if q["Symbol"] == short_sym), {})
                        q_long = next((q for q in qs if q["Symbol"] == long_sym), {})
                        
                        if q_short and q_long:
                            bid_short = float(q_short.get("Bid", 0))
                            ask_short = float(q_short.get("Ask", 0))
                            bid_long = float(q_long.get("Bid", 0))
                            ask_long = float(q_long.get("Ask", 0))
                            
                            # Credit = Bid Short - Ask Long
                            credit = bid_short - ask_long
                            risk = float(width) - credit
                            rr = (credit / risk) * 100 if risk > 0 else 0
                            breakeven = short_strike - credit if type_ == "PUT" else short_strike + credit
                            
                            return {
                                "expiry": expiry_date,
                                "dte": dte,
                                "short": short_strike,
                                "long": long_strike,
                                "credit": round(credit, 2),
                                "risk": round(risk, 2),
                                "rr": round(rr, 1),
                                "breakeven": round(breakeven, 2),
                                "short_sym": short_sym,
                                "long_sym": long_sym,
                                "bid_short": bid_short,
                                "ask_short": ask_short,
                                "bid_long": bid_long,
                                "ask_long": ask_long
                            }
                except: return None
                return None

            # 2. Parallel Execution
            tasks = [process_expiration(exp) for exp in expirations]
            results = await asyncio.gather(*tasks)
            return [r for r in results if r is not None]

        except Exception as e:
            self.log_msg(f"CHAIN ERROR: {e}")
            return []

    async def execute_spread(self, short_sym, long_sym, qty, price, stop_trigger, order_type="LIMIT", side="SELL", max_slippage=0.05):
        """
        Executes a vertical spread.
        Side: "SELL" = Credit Spread (Sell Short, Buy Long). "BUY" = Debit Spread (Buy Short, Sell Long).
        """
        # [FIX] Ensure Symbol Formatting (Defensive)
        short_sym = parse_occ_to_ts_symbol(short_sym) or short_sym
        long_sym = parse_occ_to_ts_symbol(long_sym) or long_sym

        if DRY_RUN_EXEC:
            self.log_msg(f"DRY RUN: SPREAD {short_sym}/{long_sym} (Side: {side}, Stop: {stop_trigger})")
            return "DRY_OID", None
            
        self.log_msg(f"LIVE SPREAD: {short_sym}/{long_sym} (Side: {side}, Stop: {stop_trigger})")
        try:
            if not self.TS: return None, "No TS Instance"
            account_id = YOUR_ACCOUNT_ID
            
            # Construct Legs based on Side
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
                    {"Symbol": long_sym, "Quantity": str(qty), "TradeAction": "SellToOpen", "AssetType": "Option"}
                ]
            
            # Profit Target Logic
            target_price = 0.0
            if side == "SELL":
                 target_price = round(float(price) * 0.5, 2) # Buy back cheap
            else:
                 target_price = round(float(price) * 1.5, 2) # Sell high
            
            # 1. Send Entry (Smart Walker for LIMIT)
            entry_id = None
            
            url = f"{self.TS.BASE_URL}/orderexecution/orders"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}", "Content-Type": "application/json"}

            if order_type == "LIMIT" and price:
                 self.log_msg(f"INIT SMART WALKER (SPREAD): {short_sym}/{long_sym} @ {price}")
                 
                 async def submit_spread_entry(p):
                     payload = {
                        "AccountID": account_id,
                        "OrderType": "Limit",
                        "TimeInForce": {"Duration": "Day"},
                        "Route": "Intelligent",
                        "Legs": legs,
                        "LimitPrice": f"{float(p):.2f}",
                        "TradeAction": "Buy" if side == "BUY" else "Sell" # [FIX] Ensure Top-Level Action matches Side
                     }
                     r = await asyncio.to_thread(requests.post, url, json=payload, headers=headers)
                     # self.log_msg(f"Review Payload: {payload}") # Debug
                     if r.status_code in [200, 201]:
                        d = r.json(); return d.get("Orders", [{}])[0].get("OrderID")
                     self.log_msg(f"WALKER FAIL: {r.text}")
                     return None # Wrapper will handle this by checking logic below

                 # Execute Walker
                 entry_id = await NexusExecution.smart_limit_walker(self.TS, submit_spread_entry, price, side, max_slippage=max_slippage)
            
            if not entry_id:
                # If Smart Walker was used and failed, DO NOT fallback to a passive Limit.
                # Use strict abort to respect Slippage Cap.
                if order_type == "LIMIT" and max_slippage > 0:
                     self.log_msg(f"🛑 WALKER FAILED (Slippage Cap {max_slippage}). Aborting execution.")
                     return None, "Walker Logic Failed (Slippage)"
                
                # Fallback only for MARKET or straight limits (if walker wasn't used, though logic implies it was)
                pass 
            
            # --- FALLBACK / STANDARD EXECUTION ---
            payload = {
                "AccountID": account_id,
                "OrderType": "Market" if order_type == "MARKET" else "Limit",
                "TimeInForce": {"Duration": "Day"},
                "Route": "Intelligent",
                "Legs": legs
            }
            
            if order_type != "MARKET" and price:
                payload["LimitPrice"] = f"{float(price):.2f}"
            
            self.log_msg(f"DEBUG PAYLOAD (ENTRY): {json.dumps(payload)}")
            
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
                        return None, f"API Error: {resp_text}"


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
                # [FIX] Use Regex to properly identify Call/Put 
                match = re.search(r'(?<![A-Z])[CP](?![A-Z])', short_sym) # Look for standalone C/P or C/P before digits? 
                # Better: Use the CHAIN_REGEX defined earlier or simple parse
                # SPY 260206C705
                is_put = False
                if "P" in short_sym.split(' ')[-1]: # Check only the contract part (after space)
                    is_put = True
                elif re.search(r'\d+[P]\d+', short_sym):
                    is_put = True
                
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
                
                return entry_id, None
            else:
                return None, "Entry ID missing after execution attempt"

        except Exception as e:
            self.log_msg(f"SPREAD EXCEPTION: {e}")
            return None, f"Exception: {e}"

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

    async def _get_open_orders(self):
        """Helper to fetch open orders from TradeStation."""
        try:
            url = f"https://api.tradestation.com/v3/brokerage/accounts/{YOUR_ACCOUNT_ID}/orders"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
            r = await asyncio.to_thread(requests.get, url, headers=headers)
            if r.status_code == 200:
                return r.json().get("Orders", [])
            return []
        except Exception as e:
            self.log_msg(f"Get Orders Error: {e}")
            return []

    async def close_spread(self, short_sym, long_sym, qty, side="SELL"):
        """
        Executes a Market Close for a spread (Panic Close) with SAFETY PROTOCOL.
        1. Cancels any existing open orders for these legs (GTC Limits).
        2. Submits Market Close.
        3. Prevents Double-Execution (Race Condition).
        """
        # [FIX] Sanitize Symbols
        short_sym = parse_occ_to_ts_symbol(short_sym) or short_sym
        long_sym = parse_occ_to_ts_symbol(long_sym) or long_sym
        
        self.log_msg(f"Initiating Safety Close for {short_sym}/{long_sym}...")

        # --- STEP 1: CANCEL EXISTING ORDERS (RACE CONDITION GUARD) ---
        try:
            orders = await self._get_open_orders()
            # Filter for Active Orders (ignoring Filled/Canceled)
            active_states = ["ACK", "DON", "HELD", "OSP", "STP"] # TS Statuses (ACK=Received, OSP=Open)
            # Actually TS V3 statuses: "Open", "PartiallyFilled", "Queued", "Received". 
            # We just check if it's NOT in closed states.
            closed_states = ["FLL", "REJ", "CAN", "EXP", "CLS", "Filled", "Canceled", "Expired", "Rejected", "Closed"]
            
            to_cancel = []
            for o in orders:
                status = str(o.get("Status", "")).strip()
                if status in closed_states: continue
                
                legs = o.get("Legs", [])
                for leg in legs:
                    lsym = str(leg.get("Symbol", "")).replace(" ", "")
                    target_short = str(short_sym).replace(" ", "")
                    target_long = str(long_sym).replace(" ", "")
                    
                    if lsym == target_short or lsym == target_long:
                        to_cancel.append(o.get("OrderID"))
                        break
            
            if to_cancel:
                self.log_msg(f"⚠️ SAFETY: Found {len(to_cancel)} open orders to CANCEL first.")
                for oid in to_cancel:
                    self.log_msg(f"   -> Canceling {oid}...")
                    await self.cancel_order(oid)
                # BRIEF PAUSE to allow cancel to propagate (TS API Latency)
                await asyncio.sleep(1.0) 
            else:
                self.log_msg("✅ SAFETY: No conflicting open orders found.")

        except Exception as e:
            self.log_msg(f"⚠️ SAFETY CHECK ERROR: {e}. Proceeding with close anyway.")

        # --- STEP 2: EXECUTE MARKET CLOSE ---
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

    async def execute_order(self, symbol, qty, order_type, side, price=None, account_id=None):
        if DRY_RUN_EXEC:
            self.log_msg(f"DRY RUN: {side} {qty} {symbol} @ {order_type} {price if price else 'MKT'}")
            return "DRY_OID"
            
        self.log_msg(f"LIVE ORDER: {side} {qty} {symbol} @ {order_type} (Acct: {account_id if account_id else 'Default'})")
        try:
            if not self.TS: return None
            
            target_account = account_id if account_id else YOUR_ACCOUNT_ID
            if not target_account: return None
            
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

            # [NEW] SMART EXECUTION CHECK (SINGLE LEG)
            if order_type == "LIMIT" and price:
                 self.log_msg(f"INIT SMART WALKER: {symbol} @ {price}")
                 
                 async def submit_single_leg(p):
                     # Construct Payload for this price point
                     payload = {
                        "AccountID": target_account,
                        "Symbol": symbol,
                        "Quantity": str(qty),
                        "OrderType": "Limit",
                        "TradeAction": action,
                        "AssetType": asset_type,
                        "LimitPrice": f"{float(p):.2f}",
                        "TimeInForce": {"Duration": "Day"},
                        "Route": "Intelligent"
                     }
                     # Send Request
                     r = await asyncio.to_thread(requests.post, url, json=payload, headers=headers)
                     if r.status_code in [200, 201]:
                        d = r.json(); return d.get("Orders", [{}])[0].get("OrderID")
                     return None

                 # Run Walker
                 order_id = await NexusExecution.smart_limit_walker(
                     self.TS, submit_single_leg, price, action
                 )
                 
                 if order_id:
                     self.log_msg(f"SMART EXEC SUCCESS: {symbol} (OID: {order_id})")
                     return order_id
                 else:
                     self.log_msg(f"SMART EXEC FAILED/TIMEOUT: {symbol}")
                     return None

            # --- STANDARD FALLBACK ---
            payload = {
                "AccountID": target_account,
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
        await asyncio.sleep(3)
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

                # --- JARD MOMENTUM ENGINE (Tick Velocity) ---
                now_ts = time.time()
                self.tick_window.append((now_ts, self.latest_spy_price))
                
                # Prune old ticks (>60s)
                while self.tick_window and (now_ts - self.tick_window[0][0] > 60):
                    self.tick_window.popleft()
                
                # Calculate Velocity if we have enough data (>10s)
                if len(self.tick_window) > 10:
                    start_price = self.tick_window[0][1]
                    # Simple Velocity: (Current - Start) * Scalar
                    # Scalar 20.0 roughly maps $0.50 move to Score 10
                    raw_mom = (self.latest_spy_price - start_price) * 20.0
                    self.momentum_score = max(-10.0, min(10.0, raw_mom)) # Clamp -10 to +10
                else:
                    self.momentum_score = 0.0

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

    async def send_reply(self, identity, data):
        if not identity: return
        try: await self.exec_sock.send_multipart([identity, b'', json.dumps(data).encode()])
        except Exception as e: self.log_msg(f"Reply Error: {e}")

    async def listen_for_orders(self):
        self.log_msg("Worker: Execution Gateway Active")
        while True:
            client_id = None
            try:
                frames = await self.exec_sock.recv_multipart()
                # Expect [Identity, Empty, JSON] (REQ) or [Identity, JSON] (DEALER)
                if len(frames) < 2: continue
                client_id = frames[0]
                
                # Check for empty delimiter
                content_idx = 2 if len(frames) > 2 and frames[1] == b'' else 1
                if len(frames) <= content_idx: continue
                
                try: msg = json.loads(frames[content_idx].decode())
                except: continue

                self.file_log(f"CMD RECEIVED: {msg} [ID: {client_id}]")
                
                if not self.TS or not self.TS.access_token:
                    await self.send_reply(client_id, {"status": "error", "msg": "Auth Failed"}); continue

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
                            await self.send_reply(client_id, {"status": "ok", "orders": active})
                        else: 
                            await self.send_reply(client_id, {"status": "error", "msg": f"API {r.status_code}"})
                    except Exception as e: 
                        await self.send_reply(client_id, {"status": "error", "msg": str(e)})
                    continue

                if cmd == "GET_MULTI_QUOTE":
                    try:
                        # Expects "symbols" (list of strings)
                        syms = msg.get("symbols", [])
                        if not syms:
                            await self.send_reply(client_id, {"status": "error", "msg": "No symbols"})
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
                            await self.send_reply(client_id, {"status": "ok", "quotes": q_map})
                        else:
                            await self.send_reply(client_id, {"status": "error", "msg": f"API {r.status_code}"})
                    except Exception as e:
                        await self.exec_sock.send_json({"status": "error", "msg": str(e)})
                    continue

                if cmd == "CANCEL_ORDER":
                    oid = msg.get("order_id"); self.log_msg(f"REQ: CANCEL {oid}")
                    try:
                        url = f"https://api.tradestation.com/v3/orderexecution/orders/{oid}"
                        r = await asyncio.to_thread(requests.delete, url, headers=headers)
                        if r.status_code in [200, 201]: await self.send_reply(client_id, {"status": "ok", "msg": "Cancellation Sent"})
                        else: await self.send_reply(client_id, {"status": "error", "msg": r.json().get("Message", "Failed")})
                    except Exception as e: await self.send_reply(client_id, {"status": "error", "msg": str(e)})
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
                    await self.send_reply(client_id, {"status": "ok", "msg": "Armed"})
                    continue
                
                if cmd == "DISARM":
                    if sym in self.oco_registry: del self.oco_registry[sym]
                    self.log_msg(f"DISARMED: {sym}")
                    self.dump_active_targets()
                    await self.send_reply(client_id, {"status": "ok", "msg": "Disarmed"})
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
                    await self.send_reply(client_id, {"status": "ok", "msg": "Smart Exit Started"})
                    continue

                # --- SPREAD SNIPER COMMANDS ---
                elif cmd == "GET_MANAGED_SPREADS":
                    # Return full registry values to allow UI to group legs
                    # Convert dict_values to list
                    spreads = list(self.oco_registry.values())
                    await self.send_reply(client_id, {"status": "ok", "spreads": spreads})
                    continue
                
                elif cmd == "GET_POSITIONS":
                    try:
                        acc_id = msg.get("account_id")
                        if not acc_id: acc_id = YOUR_ACCOUNT_ID
                        
                        # CACHE LOGIC (Stop Flickering)
                        now_ts = time.time()
                        if not hasattr(self, "_pos_cache"): self._pos_cache = {}
                        
                        # If cached < 2s ago and not empty, return cache
                        last_ts, last_data = self._pos_cache.get(acc_id, (0, []))
                        if now_ts - last_ts < 2.0 and len(last_data) > 0:
                            self.log_msg(f"DEBUG: Returning cached positions for {acc_id} ({len(last_data)})")
                            await self.send_reply(client_id, {"status": "ok", "positions": last_data})
                            continue

                        self.log_msg(f"DEBUG: Fetching positions for {acc_id}...")
                        positions = await asyncio.to_thread(self.TS.get_positions, acc_id)
                        
                        self.log_msg(f"RAW POSITIONS for {acc_id}: {positions}") # [DEBUG] INJECTED

                        # Update Cache if valid
                        if positions is not None:
                            self._pos_cache[acc_id] = (now_ts, positions)
                        
                        # self.log_msg(f"DEBUG: Got {len(positions)} positions. Sending reply...")
                        await self.send_reply(client_id, {"status": "ok", "positions": positions})
                        # self.log_msg("DEBUG: Reply sent successfully.")
                    except Exception as e:
                        self.log_msg(f"DEBUG: Error fetching positions: {e}")
                        await self.send_reply(client_id, {"status": "error", "msg": str(e)})
                    continue

                elif cmd == "GET_CHAIN":
                    ticker = msg.get("ticker", "SPY")
                    strike = msg.get("strike")
                    width = msg.get("width")
                    type_ = msg.get("type", "PUT")
                    
                    # Parallel Fetch: Chain + IVR
                    chain_task = self.fetch_option_chain(ticker, strike, width, type_)
                    ivr_task = self.fetch_orats_ivr(ticker)
                    
                    data, (iv, ivr) = await asyncio.gather(chain_task, ivr_task)

                    # Ensure we have price
                    price = self.latest_spy_price
                    if price <= 0:
                        # Try simple fetch if missing
                        try:
                             url = f"{self.TS.BASE_URL}/marketdata/quotes/{ticker}"
                             headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
                             # Helper synchronous request in async flow (ok for quick patch)
                             # [FIX] Replaced blocking sync call with async + timeout
                             # import requests
                             # r = requests.get(url, headers=headers)
                             r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=5)
                             if r.status_code == 200:
                                 q = r.json().get("Quotes", [])
                                 if q: price = float(q[0].get("Last", 0))
                                 self.latest_spy_price = price
                        except: pass
                    
                    # Attach Price to response
                    await self.send_reply(client_id, {"status": "ok", "data": data, "iv": iv, "ivr": ivr, "price": price})
                    continue

                if cmd == "EXECUTE_SPREAD":
                    self.log_msg(f"ARGS: {msg}") # Trace Incoming Payload
                    self.log_msg(f"⚡ [TRACE] EXECUTE_SPREAD RECEIVED. Side: {msg.get('side')} Syms: {msg.get('short_sym')}/{msg.get('long_sym')}")
                    short_sym = msg.get("short_sym")
                    long_sym = msg.get("long_sym")
                    qty = int(msg.get("qty", 1))
                    price = msg.get("price")
                    stop_trigger = msg.get("stop_trigger")
                    order_type = msg.get("order_type", "LIMIT")
                    side = msg.get("side", "SELL")
                    
                    max_slippage = float(msg.get("max_slippage", 0.05))
                    max_slippage = float(msg.get("max_slippage", 0.05))
                    oid, err_msg = await self.execute_spread(short_sym, long_sym, qty, price, stop_trigger, order_type, side, max_slippage)
                    if oid:
                        await self.send_reply(client_id, {"status": "ok", "order_id": oid})
                    else:
                        await self.send_reply(client_id, {"status": "error", "msg": f"Exec Fail: {err_msg}"})
                    continue

                if cmd == "CLOSE_SPREAD":
                    self.log_msg(f"🔍 [TRACE] RECEIVED CLOSE_SPREAD: {msg}")
                    try:
                        short_sym = msg.get("short_sym")
                        long_sym = msg.get("long_sym")
                        qty = int(msg.get("qty", 1))
                        side = msg.get("side", "SELL")
                        
                        self.log_msg(f"   -> Parsed: {short_sym}/{long_sym} (Side: {side})")
                        
                        # Use call_soon to avoid blocking? No, create_task is better for async.
                        task = asyncio.create_task(self.close_spread(short_sym, long_sym, qty, side))
                        # Add callback to log task failure?
                        def handle_result(fut):
                            try: fut.result()
                            except Exception as e: self.log_msg(f"💥 [TRACE] CLOSE_SPREAD TASK FAILED: {e}")
                        task.add_done_callback(handle_result)
                        
                        await self.send_reply(client_id, {"status": "ok", "msg": "Close Sent"})
                    except Exception as e:
                        self.log_msg(f"💥 [TRACE] CLOSE_SPREAD PARSE/DISPATCH ERROR: {e}")
                        await self.send_reply(client_id, {"status": "error", "msg": str(e)})
                    continue

                # GENERIC EXECUTE WRAPPER
                # We need to map the generic execute_order call to the specific API call logic
                # But wait, execute_order is defined in this class now.
                # However, execute_order takes (symbol, qty, order_type, side, price)
                # We need to map 'cmd' (BUY/SELL) to 'side'.
                # [MODIFIED] Force MARKET as requested by user
                # res = await self.execute_order(sym, qty, msg.get("type", "MARKET"), cmd, limit)
                res = await self.execute_order(sym, qty, "MARKET", cmd, None, account_id=msg.get("account_id"))
                
                res = await self.execute_order(sym, qty, "MARKET", cmd, None, account_id=msg.get("account_id"))
                
                if res and isinstance(res, dict) and res.get("error"): 
                    await self.send_reply(client_id, {"status": "error", "msg": res["error"]})
                elif res and isinstance(res, str): 
                    await self.send_reply(client_id, {"status": "ok", "id": res, "order_status": "SENT"})
                elif res: 
                    # Fallback for unexpected types
                     await self.send_reply(client_id, {"status": "ok", "id": str(res), "order_status": "SENT"})
                else: 
                    await self.send_reply(client_id, {"status": "error", "msg": "Unknown Error (Check Logs)"})

            except Exception as e:
                self.log_msg(f"ERR: {e}"); 
                try: await self.send_reply(client_id, {"status": "error", "msg": str(e)})
                except: pass

    def auto_arm_spreads(self, positions):
        """
        Scans positions for unmanaged vertical spreads and automatically creates risk rules.
        """
        # 1. Group positions by Expiry
        expiry_groups = {}
        for p in positions:
            sym = p.get("Symbol", "")
            try:
                # Format: SPY 260220P660
                parts = sym.split(' ')
                if len(parts) > 1:
                    code = parts[1] # 260220P660
                    expiry = code[:6]
                    if expiry not in expiry_groups: expiry_groups[expiry] = []
                    expiry_groups[expiry].append(p)
            except: pass

        # 2. Iterate Groups to find Spreads
        for expiry, group in expiry_groups.items():
            calls = [x for x in group if "C" in x.get("Symbol").split(' ')[1]]
            puts = [x for x in group if "P" in x.get("Symbol").split(' ')[1]]
            
            # Helper to get strike
            def get_k(s):
                import re
                m = re.search(r'[CP]([\d.]+)$', s)
                return float(m.group(1)) if m else 0

            # --- PROCESS PUTS ---
            short_puts = [p for p in puts if int(p.get("Quantity", 0)) < 0]
            long_puts = [p for p in puts if int(p.get("Quantity", 0)) > 0]
            
            for s in short_puts:
                s_sym = s.get("Symbol")
                # Skip if already managed
                if s_sym in self.oco_registry: continue
                
                k_short = get_k(s_sym)
                qty = abs(int(s.get("Quantity")))
                
                # Check for Long Pair
                match = None
                is_credit = False
                for l in long_puts:
                    if l.get("Symbol") == s_sym: continue
                    k_long = get_k(l.get("Symbol"))
                    
                    if k_long < k_short: # Bull Put (Credit)
                        match = l; is_credit = True; break
                    elif k_long > k_short: # Bear Put (Debit)
                        match = l; is_credit = False; break
                
                if match:
                    l_sym = match.get("Symbol")
                    self.log_msg(f"✨ [AUTO-ARM] Found Unmanaged {'Credit' if is_credit else 'Debit'} Put Spread: {s_sym}/{l_sym}")
                    
                    # Create Rule
                    rule = {
                        "type": "SPREAD",
                        "short_sym": s_sym,
                        "long_sym": l_sym,
                        "qty": qty,
                        "armed": True,
                        "is_put": True,
                        "side": "SELL" if is_credit else "BUY",
                        "is_bullish": True if is_credit else False # Bull Put or Bear Put (Debit)
                    }
                    
                    # Stop Logic (BREACH TOLERANCE)
                    if is_credit:
                        # Bull Put: Stop if Price Drops < Short Strike - 0.5
                        rule["stop_trigger"] = k_short - 0.5 
                    else:
                        rule["stop_trigger"] = get_k(l_sym) * 1.02 # Debit Hedge Stop (Loose)
                        
                    self.oco_registry[s_sym] = rule
                    self.dump_active_targets()
                    self.log_msg(f"✅ Auto-Armed {s_sym}: Stop {rule['stop_trigger']}")

            # --- PROCESS CALLS ---
            short_calls = [c for c in calls if int(c.get("Quantity", 0)) < 0]
            long_calls = [c for c in calls if int(c.get("Quantity", 0)) > 0]
            
            for s in short_calls:
                s_sym = s.get("Symbol")
                if s_sym in self.oco_registry: continue
                
                k_short = get_k(s_sym)
                qty = abs(int(s.get("Quantity")))
                
                match = None
                is_credit = False
                for l in long_calls:
                    if l.get("Symbol") == s_sym: continue
                    k_long = get_k(l.get("Symbol"))
                    
                    if k_long > k_short: # Bear Call (Credit)
                        match = l; is_credit = True; break
                    elif k_long < k_short: # Bull Call (Debit)
                        match = l; is_credit = False; break
                
                if match:
                    l_sym = match.get("Symbol")
                    self.log_msg(f"✨ [AUTO-ARM] Found Unmanaged {'Credit' if is_credit else 'Debit'} Call Spread: {s_sym}/{l_sym}")
                    
                    rule = {
                        "type": "SPREAD",
                        "short_sym": s_sym,
                        "long_sym": l_sym,
                        "qty": qty,
                        "armed": True,
                        "is_put": False,
                        "side": "SELL" if is_credit else "BUY",
                        "is_bullish": False if is_credit else True
                    }
                    
                    # Stop Logic (BREACH TOLERANCE: Stop AFTER ITM)
                    # User feedback: "Should have stopped at 679.5" (Strike 679)
                    # Previous logic was Strike - 0.5 (Pre-breach). Too aggressive/confusing.
                    
                    if is_credit:
                        # Bear Call: Stop if Price Rises > Short Strike + 0.5
                        rule["stop_trigger"] = k_short + 0.5 
                    else:
                        # Bull Call: Stop if Price Drops < Long Strike
                        rule["stop_trigger"] = get_k(l_sym) * 0.99
                        
                    self.oco_registry[s_sym] = rule
                    self.dump_active_targets()
                    self.log_msg(f"✅ Auto-Armed {s_sym}: Stop {rule['stop_trigger']} ({'Credit' if is_credit else 'Debit'})")
                    self.dump_active_targets()
                    self.log_msg(f"✅ Auto-Armed {s_sym}: Stop {rule['stop_trigger']}")

    def check_spread_profit(self, positions):
        """
        Refactored 50% Profit Guard logic.
        """
        pos_map = {str(p.get("Symbol", "")).replace(" ", ""): p for p in positions}
                         
        for sym, rule in list(self.oco_registry.items()):
             if rule.get("type") == "SPREAD" and rule.get("armed"):
                 short_sym = str(rule.get("short_sym", "")).replace(" ", "")
                 long_sym = str(rule.get("long_sym", "")).replace(" ", "")
                 
                 if short_sym in pos_map and long_sym in pos_map:
                     p_short = pos_map[short_sym]
                     p_long = pos_map[long_sym]
                     
                     q_short = int(p_short.get("Quantity", 0))
                     q_long = int(p_long.get("Quantity", 0))
                     rule_qty = int(rule.get("qty", 1))
                     safe_qty = min(abs(q_short), abs(q_long), rule_qty)
                     
                     if safe_qty < 1: continue

                     pl_net = float(p_short.get("UnrealizedProfitLoss", 0)) + float(p_long.get("UnrealizedProfitLoss", 0))
                     val_net = float(p_short.get("MarketValue", 0)) + float(p_long.get("MarketValue", 0))
                     cost_basis = val_net - pl_net
                     check_basis = abs(cost_basis)
                     
                     pct = 0.0
                     if check_basis > 0: pct = (pl_net / check_basis) * 100
                     
                     # Throttle Log
                     now_ts = time.time()
                     last_chk = rule.get("last_check_log", 0)
                     if now_ts - last_chk > 60:
                         side_lbl = "CREDIT" if rule.get("side") == "SELL" else "DEBIT"
                         self.log_msg(f"🕵️ [AUTO-MGR] Checking {short_sym} ({side_lbl}) | Net P/L: {pct:.1f}% (Qty: {safe_qty})")
                         rule["last_check_log"] = now_ts
                     
                     if pct >= 50.0:
                         if self.is_valid_trigger_time():
                             self.log_msg(f"💸 [AUTO-PROFIT] {short_sym} spread is up {pct:.1f}%. Triggering Close!")
                             asyncio.create_task(self.close_spread(short_sym, long_sym, safe_qty, rule.get("side", "SELL")))
                             self.oco_registry[sym]["armed"] = False 
                             self.dump_active_targets()
                         else:
                             if now_ts - getattr(self, "last_ah_log", 0) > 60:
                                 self.log_msg(f"⏸️ [AFTER HOURS] {short_sym} spread is up {pct:.1f}% (Target Met). Holding until open.")
                                 self.last_ah_log = now_ts

    async def stream_account_positions(self):
        """
        Replaces poll_account_data. Streams position updates in real-time.
        """
        self.log_msg("Stream: Account Positions ACTIVE")
        while True:
            try:
                if not self.TS or not self.TS.access_token: 
                    await asyncio.sleep(5); continue

                # Streaming Endpoint
                url = f"{self.TS.BASE_URL}/brokerage/stream/accounts/{YOUR_ACCOUNT_ID}/positions"
                headers = {"Authorization": f"Bearer {self.TS.access_token}"}
                ssl_ctx = ssl.create_default_context(); ssl_ctx.check_hostname=False; ssl_ctx.verify_mode=ssl.CERT_NONE
                
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
                    async with s.get(url, headers=headers, timeout=None) as r:
                        if r.status == 200:
                            async for line in r.content:
                                if not line: continue
                                try:
                                    # Streaming API sends updates, not full snapshots.
                                    # However, checks show it might send the full list or diffs.
                                    # Wait, Documentation says "Stream of Position objects".
                                    # We need to maintain state.
                                    
                                    # Actually, for V3, let's treat each message as a state update event.
                                    # But since we need the FULL PORTFOLIO for spread grouping to work (Short+Long),
                                    # Relaying solitary updates might break the logic if we don't have the full state.
                                    
                                    # HYBRID APPROACH:
                                    # On any stream event, trigger a fast SNAPSHOT fetch.
                                    # [FIX] Throttle to prevent 429 Avalanche (Max 1 sync per 2s)
                                    now = time.time()
                                    if hasattr(self, 'last_stream_sync') and (now - self.last_stream_sync < 2.0):
                                        continue # Skip this event, we just synced
                                        
                                    self.last_stream_sync = now

                                    # TRIGGER SYNC
                                    balances = await asyncio.to_thread(self.TS.get_account_balances)
                                    # [FIX] Force Account ID here too
                                    positions = await asyncio.to_thread(self.TS.get_positions, YOUR_ACCOUNT_ID)
                                    
                                    # self.log_msg(f"STREAM SYNC: {len(positions)} positions for {YOUR_ACCOUNT_ID}") # [DEBUG] SILENCED
                                    
                                    # Update Internal Position Map
                                    self.positions = {}
                                    for p in positions:
                                        try:
                                            s = p.get("Symbol")
                                            q = int(p.get("Quantity", 0))
                                            self.positions[s] = q
                                        except: pass
                                        
                                    # [FIX] MULTI-ACCOUNT AGGREGATION
                                    # We need to fetch Futures Account 210VGM01 too
                                    try:
                                        # 1. Main Account
                                        bal_main = balances[0] if balances else {}
                                        equity_main = self._to_float(bal_main.get('Equity', 0))
                                        ytd_main = equity_main - 52648.47
                                        
                                        # 2. Futures Account
                                        bal_fut_list = await asyncio.to_thread(self.TS.get_account_balances, "210VGM01")
                                        bal_fut = bal_fut_list[0] if bal_fut_list else {}
                                        equity_fut = self._to_float(bal_fut.get('Equity', 0))
                                        
                                        # [FIX] Merge Positions First
                                        pos_fut = await asyncio.to_thread(self.TS.get_positions, "210VGM01")
                                        all_positions = list(positions)
                                        if pos_fut: all_positions.extend(pos_fut)
                                        
                                        # 3. Aggregate
                                        agg_equity = equity_main + equity_fut
                                        # [FIX] Calc PNL from Positions
                                        agg_unrealized = sum(self._to_float(pos.get('UnrealizedProfitLoss', 0)) for pos in all_positions)
                                        agg_realized = self._to_float(bal_main.get('RealizedProfitLoss', 0)) + self._to_float(bal_fut.get('RealizedProfitLoss', 0))
                                        
                                        # [FIX] Global YTD Calculation (Grand Total Start: $52,648.47)
                                        agg_ytd = agg_equity - 52648.47
                                        
                                        # Todays PNL (Sum of both)
                                        todays_main = self._to_float(bal_main.get('TodaysProfitLoss', 0))
                                        todays_fut = self._to_float(bal_fut.get('TodaysProfitLoss', 0))
                                        agg_todays = todays_main + todays_fut
                                        
                                        agg_bp = self._to_float(bal_main.get('BuyingPower', 0)) + self._to_float(bal_fut.get('BuyingPower', 0))
                                        agg_exp = (self._to_float(bal_main.get('MktValue', 0)) if bal_main.get('MktValue') else self._to_float(bal_main.get('MarketValue', 0))) + \
                                                  (self._to_float(bal_fut.get('MktValue', 0)) if bal_fut.get('MktValue') else self._to_float(bal_fut.get('MarketValue', 0)))

                                        payload = {
                                            "total_account_value": agg_equity,
                                            "unrealized_pnl": agg_unrealized,
                                            "realized_pnl": agg_realized,
                                            "ytd_pnl": agg_ytd,
                                            "todays_pnl": agg_todays,
                                            "buying_power": agg_bp,
                                            "value_of_open_positions": agg_exp,
                                            "positions": all_positions
                                        }
                                        
                                    except Exception as e:
                                        self.log_msg(f"AGGREGATION ERROR: {e}")
                                        # Fallback to single account
                                        b = balances[0] if balances else {}
                                        payload = {
                                            "total_account_value": self._to_float(b.get('Equity', 0)),
                                            "unrealized_pnl": self._to_float(b.get('UnrealizedProfitLoss', 0)),
                                            "positions": positions
                                        }

                                    self.last_acct_payload = payload
                                    await self.account_sock.send_multipart([b"A", json.dumps(payload).encode('utf-8')])
                                    
                                    self.auto_arm_spreads(payload["positions"])
                                    self.check_spread_profit(payload["positions"])
                                    
                                    await asyncio.sleep(0.01) 
                                    
                                except Exception as e:
                                    # self.log_msg(f"Stream Parse Error: {e}")
                                    pass
                        else:
                            # self.log_msg(f"Acct Stream Error: {r.status}")
                            await asyncio.sleep(5)
            except Exception as e: 
                # self.log_msg(f"Acct Stream Exception: {e}")
                await asyncio.sleep(5)

    async def poll_account_positions(self):
        """
        Secondary Polling Loop: Fetches positions every 2 minutes to ensure
        freshness even if the WebSocket stream hangs or goes silent.
        """
        self.log_msg("Init: Account Poller Active (120s)")
        await asyncio.sleep(10) # [FIX] Initial Delay to avoid startup collision with Stream
        
        while True:
            try:
                if not self.TS or not self.TS.access_token:
                    await asyncio.sleep(5)
                    continue

                # Fetch Data (Threaded to avoid blocking)
                balances = await asyncio.to_thread(self.TS.get_account_balances)
                # [FIX] Explictly pass YOUR_ACCOUNT_ID to avoid default account issues
                positions = await asyncio.to_thread(self.TS.get_positions, YOUR_ACCOUNT_ID)
                
                self.log_msg(f"POLL DEBUG: Fetched {len(positions)} positions for {YOUR_ACCOUNT_ID}")

                # Update Internal Map
                self.positions = {}
                for p in positions:
                    try:
                        s = p.get("Symbol")
                        q = int(p.get("Quantity", 0))
                        self.positions[s] = q
                    except: pass
                
                # Construct Payload (AGGREGATED)
                try:
                    # 1. Main Account
                    bal_main = balances[0] if balances else {}
                    equity_main = self._to_float(bal_main.get('Equity', 0))
                    ytd_main = equity_main - 52648.47
                    
                    # 2. Futures Account
                    bal_fut_list = await asyncio.to_thread(self.TS.get_account_balances, "210VGM01")
                    bal_fut = bal_fut_list[0] if bal_fut_list else {}
                    equity_fut = self._to_float(bal_fut.get('Equity', 0))
                    
                    # [FIX] Merge Positions First
                    pos_fut = await asyncio.to_thread(self.TS.get_positions, "210VGM01")
                    all_positions = list(positions)
                    if pos_fut: all_positions.extend(pos_fut)
                    
                    # 3. Aggregate
                    agg_equity = equity_main + equity_fut
                    # [FIX] Calc PNL from Positions
                    agg_unrealized = sum(self._to_float(pos.get('UnrealizedProfitLoss', 0)) for pos in all_positions)
                    
                    agg_realized = self._to_float(bal_main.get('RealizedProfitLoss', 0)) + self._to_float(bal_fut.get('RealizedProfitLoss', 0))
                    
                    # [FIX] Global YTD Calculation (Grand Total Start: $52,648.47)
                    agg_ytd = agg_equity - 52648.47
                    
                    # Todays PNL
                    todays_main = self._to_float(bal_main.get('TodaysProfitLoss', 0))
                    todays_fut = self._to_float(bal_fut.get('TodaysProfitLoss', 0))
                    agg_todays = todays_main + todays_fut
                    
                    agg_bp = self._to_float(bal_main.get('BuyingPower', 0)) + self._to_float(bal_fut.get('BuyingPower', 0))
                    agg_exp = (self._to_float(bal_main.get('MktValue', 0)) if bal_main.get('MktValue') else self._to_float(bal_main.get('MarketValue', 0))) + \
                              (self._to_float(bal_fut.get('MktValue', 0)) if bal_fut.get('MktValue') else self._to_float(bal_fut.get('MarketValue', 0)))

                    payload = {
                        "total_account_value": agg_equity,
                        "unrealized_pnl": agg_unrealized,
                        "realized_pnl": agg_realized,
                        "ytd_pnl": agg_ytd,
                        "todays_pnl": agg_todays,
                        "buying_power": agg_bp,
                        "value_of_open_positions": agg_exp,
                        "positions": all_positions
                    }
                    
                except Exception as e:
                    self.log_msg(f"POLL AGGREGATION ERROR: {e}")
                    # Fallback
                    b = balances[0] if balances else {}
                    payload = {"total_account_value": self._to_float(b.get('Equity', 0)), "positions": positions}

                # Cache & Broadcast
                self.last_acct_payload = payload
                await self.account_sock.send_multipart([b"A", json.dumps(payload).encode('utf-8')])
                
                # [FIX] Dump active_portfolio.json for nexus_greeks.py
                antigravity_dump("active_portfolio.json", payload)
                
                # Trigger internal logic
                self.auto_arm_spreads(payload["positions"])
                self.check_spread_profit(payload["positions"])
                
                self.log_msg(f"POLL: Refreshed {len(positions)} positions (Backup Routine)")
                
                # Wait for next cycle (2 minutes)
                await asyncio.sleep(120)

            except Exception as e:
                self.log_msg(f"POLL ERROR: {e}")
                await asyncio.sleep(5)

    async def stream_three_minute_bars(self):
        while True:
            try:
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
                if last is not None: 
                    # Wide format: " 6,967.00 "
                    p_str = f"{float(last):,.2f}"
                    dt.update_cell_at((r,1), f" {p_str} ")
                
                if chg is not None: 
                    # Wide format: " +0.00% "
                    c_val = float(chg)
                    c_str = f"{c_val:+.2f}%"
                    dt.update_cell_at((r,2), Text(f" {c_str} ", style="green" if c_val>0 else "red"))
                
                dt.update_cell_at((r,3), f" {datetime.datetime.now().strftime('%H:%M:%S')} ")
            except: pass

        async def on_mount(self):
            # Set Mode Indicator
            mi = self.query_one("#mode_indicator", Static)
            if DRY_RUN_EXEC:
                mi.update("🟢 DRY RUN")
                mi.styles.background = "#008000"; mi.styles.color = "white"
            else:
                mi.update("🔴 LIVE")
                mi.styles.background = "#D90429"; mi.styles.color = "white"

            dt = self.query_one("#ticker_table", DataTable)
            # Wide Headers to force column width
            dt.add_columns("SYMBOL", "LAST PRICE      ", "CHANGE %    ", "TIME CHECK"); dt.cursor_type = "none"
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