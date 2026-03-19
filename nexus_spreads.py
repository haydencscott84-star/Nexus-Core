import sys
import zmq
import zmq.asyncio
import asyncio
import datetime
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Button, Input, Label, Select, Static, Log
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.screen import Screen, ModalScreen
from textual import work, on
from rich.text import Text

# --- MODAL ---
class CloseConfirmModal(ModalScreen):
    def __init__(self, message, on_confirm):
        super().__init__()
        self.message = message
        self.on_confirm = on_confirm

    def compose(self) -> ComposeResult:
        with Container(classes="modal-dialog"):
            yield Label(self.message, classes="modal-msg")
            with Horizontal(classes="modal-buttons"):
                yield Button("CONFIRM CLOSE", variant="error", id="btn_confirm")
                yield Button("CANCEL", variant="primary", id="btn_cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_confirm":
            self.dismiss(True)
            self.on_confirm()
        else:
            self.dismiss(False)

# --- CONFIG ---
ZMQ_PORT_EXEC = 5567
ZMQ_PORT_MARKET = 5555
ZMQ_PORT_ACCOUNT = 5566

class SpreadSniperApp(App):
    CSS = """
    Screen { background: #111; }
    
    /* HEADER */
    #control_bar {
        dock: top;
        height: 3;
        background: #222;
        border-bottom: solid #0f0;
        padding: 0 1;
        align: left middle;
    }
    
    .control-item { margin-right: 2; }
    .control-item-right { margin-left: 4; color: #88c0d0; text-style: bold; content-align: right middle; width: 1fr; }
    #type_select { width: 12; }
    #strike_input { width: 10; }
    #width_input { width: 8; }
    #fetch_btn { background: #004400; color: #0f0; text-style: bold; border: none; }
    
    /* MAIN GRID */
    #main_grid {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 3fr 1fr;
        grid-rows: 2fr 1fr;
    }
    
    /* LEFT PANE: CHAIN TABLE */
    #chain_container {
        row-span: 1;
        column-span: 1;
        border: solid #444;
        background: #111;
    }
    
    /* RIGHT PANE: EXECUTION */
    #exec_container {
        row-span: 2;
        column-span: 1;
        border-left: solid #0f0;
        background: #1a1a1a;
        padding: 1;
    }
    
    /* BOTTOM PANE: POSITIONS & LOG */
    #bottom_container {
        row-span: 1;
        column-span: 1;
        layout: vertical;
    }
    
    #positions_table {
        border-top: solid #444;
        height: 1fr;
        width: 100%;
    }
    
    #activity_log {
        border-top: solid #444;
        border-left: solid #444;
        height: 1fr;
        width: 100%;
        background: #000;
        overflow-x: auto; /* Enable horizontal scroll */
    }

    /* EXECUTION WIDGETS */
    .exec-label { color: #888; margin-top: 1; }
    .exec-value { color: #fff; text-style: bold; margin-bottom: 1; }
    
    #execute_btn {
        width: 100%;
        background: #008000;
        color: white;
        text-style: bold;
        margin-top: 2;
        height: 3;
    }
    
    #cancel_btn {
        width: 100%;
        background: #b00;
        color: white;
        text-style: bold;
        margin-top: 1;
    }
    
    #spy_price_display {
        background: #222;
        color: #0f0;
        text-align: center;
        text-style: bold;
        padding: 1;
        border: solid #0f0;
        margin-bottom: 2;
    }
    
    /* MODAL */
    .modal-dialog {
        padding: 2;
        background: #333;
        border: solid red;
        width: 60%;
        height: auto;
        align: center middle;
    }
    .modal-msg {
        content-align: center middle;
        margin-bottom: 2;
        text-style: bold;
        color: white;
    }
    .modal-buttons {
        align: center middle;
        height: 3;
    }
    #btn_confirm { margin-right: 2; background: #b00; }
    #btn_cancel { margin-left: 2; background: #444; }
    """

    def __init__(self):
        super().__init__()
        self.zmq_ctx = zmq.asyncio.Context()
        self.req_sock = self.zmq_ctx.socket(zmq.REQ)
        self.req_sock.setsockopt(zmq.LINGER, 0) # [FIX] Prevent socket hang
        self.req_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
        
        self.sub_sock = self.zmq_ctx.socket(zmq.SUB)
        self.sub_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_MARKET}")
        self.sub_sock.subscribe(b"SPY")
        
        self.acct_sock = self.zmq_ctx.socket(zmq.SUB)
        self.acct_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_ACCOUNT}")
        self.acct_sock.subscribe(b"A")

        self.current_spy_price = 0.0
        self.selected_spread = None
        self.managed_spreads = {} # Dict of short_sym -> spread_details
        self.backend_spreads = {} # Authoritative data from Backend (ts_nexus)
        self.account_metrics = {"equity": 0, "pl": 0, "exposure": 0}

    def reconnect_req_socket(self):
        """Destroys and recreates the REQ socket to clear EFSM errors."""
        try:
            self.req_sock.close()
            self.req_sock = self.zmq_ctx.socket(zmq.REQ)
            self.req_sock.setsockopt(zmq.LINGER, 0)
            self.req_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
            self.log_msg(f"⚠️ ZMQ REQ Socket Reset (Port {ZMQ_PORT_EXEC}).")
        except Exception as e:
            self.log_msg(f"Reset Error: {e}")

    async def robust_send(self, payload, timeout_ms=3500):
        """Sends a request and waits for reply with timeout + Reset logic."""
        try:
            await self.req_sock.send_json(payload)
            if await self.req_sock.poll(timeout_ms):
                reply = await self.req_sock.recv_json()
                return reply
            else:
                self.log_msg("⚠️ Timeout: No Reply from Backend.")
                self.reconnect_req_socket()
                return None
        except zmq.ZMQError as e:
             self.log_msg(f"ZMQ Error: {e}")
             self.reconnect_req_socket()
             return None
        except Exception as e:
             self.log_msg(f"Socket Error: {e}")
             self.reconnect_req_socket()
             return None

    def compose(self) -> ComposeResult:
        # Header
        with Horizontal(id="control_bar"):
            yield Select.from_values(["PUT", "CALL"], allow_blank=False, value="PUT", id="type_select", classes="control-item")
            yield Input(placeholder="Strike", id="strike_input", classes="control-item")
            yield Input(placeholder="Width", value="5", id="width_input", classes="control-item")
            yield Button("FETCH CHAIN", id="fetch_btn", classes="control-item")
            yield Button("↻ REFRESH", id="refresh_btn", classes="control-item")
            yield Label("IV: --% | IVR: --", id="lbl_iv_status", classes="control-item")
            yield Static("ACCT: ---", id="acct_display", classes="control-item-right")

        # Main Layout
        with Grid(id="main_grid"):
            # Top Left: Option Chain
            with Vertical(id="chain_container"):
                yield Label(" OPTION CHAIN", classes="panel-header")
                yield DataTable(id="chain_table")
            
            # Right Sidebar: Execution
            with Vertical(id="exec_container"):
                yield Static("SPY: ---", id="spy_price_display")
                
                yield Label("SELECTED SPREAD:", classes="exec-label")
                yield Static("-", id="lbl_spread", classes="exec-value")
                
                yield Label("CREDIT:", classes="exec-label")
                yield Static("-", id="lbl_credit", classes="exec-value")
                
                yield Label("RISK:", classes="exec-label")
                yield Static("-", id="lbl_risk", classes="exec-value")
                
                yield Label("YIELD:", classes="exec-label")
                yield Static("-", id="lbl_yield", classes="exec-value")
                
                yield Label("STOP TRIGGER (Und.):", classes="exec-label")
                yield Static("-", id="lbl_stop", classes="exec-value")
                
                yield Label("LOT SIZE:", classes="exec-label")
                yield Input(value="1", id="qty_input", classes="control-item")
                
                yield Button("SELL TO OPEN (CREDIT)", id="execute_btn", disabled=True)
                yield Button("BUY TO OPEN (DEBIT)", id="execute_buy_btn", disabled=True)
                yield Button("PANIC CLOSE (MKT)", id="cancel_btn", disabled=True) # Logic to close selected position?

            # Bottom: Positions & Log (Stacked)
            with Vertical(id="bottom_container"):
                with Vertical():
                    yield Label(" OPEN POSITIONS", classes="panel-header")
                    yield DataTable(id="positions_table")
                with Vertical():
                    yield Label(" SYSTEM LOG", classes="panel-header")
                    yield Log(id="activity_log")

    async def on_mount(self):
        # Setup Tables
        chain_table = self.query_one("#chain_table", DataTable)
        chain_table.cursor_type = "row"
        chain_table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.")
        
        pos_table = self.query_one("#positions_table", DataTable)
        pos_table.cursor_type = "row"
        pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")
        
        self.log_msg("System Ready. Waiting for data...")
        self.fetch_last_known_price() # FALLBACK: Load last price immediately
        self.run_worker(self.market_data_loop)
        self.run_worker(self.account_data_loop)
        self.run_worker(self.fetch_managed_spreads_loop)
        self.run_worker(self.force_refresh_loop) # Active Refresh
        self.run_worker(self.active_quote_loop) # Live Spread Pricing
        self.run_worker(self.status_scheduler_loop)
        # Delay launch announcement to allow data fetch
        self.run_worker(self.delayed_launch_announce)

    async def delayed_launch_announce(self):
        await asyncio.sleep(10) # Wait for RPC
        await self.announce_status('LAUNCH')

    async def status_scheduler_loop(self):
        """Checks time for scheduled status announcements."""
        import pytz
        while True:
            await asyncio.sleep(60)
            try:
                now_et = datetime.datetime.now(pytz.timezone('US/Eastern') if pytz else None)
                t_str = now_et.strftime("%H:%M")
                if t_str == "09:30":
                    await self.announce_status("MARKET_OPEN")
                    await asyncio.sleep(60)
                if t_str == "16:00":
                    await self.announce_status("MARKET_CLOSE")
                    await asyncio.sleep(60)
            except: pass

    async def announce_status(self, reason="UPDATE"):
        """Compiles active Credit positions and posts to Discord."""
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            if self.managed_spreads:
                for sym, data in self.managed_spreads.items():
                    try:
                        k_short = data.get("short_strike", 0)
                        k_long = data.get("long_strike", 0)
                        is_put = (data.get("type") == "PUT")
                        strat_type = "Credit Put" if is_put else "Credit Call"
                        qty = data.get("qty", 1)
                        
                        strikes = f"{k_short}/{k_long}"
                        
                        # Calculate Stop
                        stop_lvl = (k_short + 0.5) if is_put else (k_short - 0.5)
                        if not is_credit: # Debit Stop Logic (Inverse)
                            # Debit Put (Long Put): Stop if price rises (Above Long Strike?)
                            # Debit Call (Long Call): Stop if price drops (Below Long Strike?)
                            stop_lvl = (k_long + 0.5) if is_put else (k_long - 0.5)
                        
                        pos_str = f"**{strat_type}** {strikes} (x{qty})\nSTOP: {stop_lvl:.2f} | PT: 50% Max | **ARMED**"
                        positions.append(pos_str)
                    except: continue

            if not positions:
                if reason == "LAUNCH":
                    msg = (f"**Nexus Credit Sniper Online**\n"
                           f"Bot Status:\n"
                           f"• Credit Call: **READY**\n"
                           f"• Credit Put: **READY**\n"
                           f"• Debit Call: **READY**\n"
                           f"• Debit Put: **READY**\n"
                           f"Active Positions: None.")
                else: 
                     if reason in ["MARKET_OPEN", "MARKET_CLOSE"]:
                         msg = f"**Nexus Credit Status ({reason})**\nSystem Active. No Open Positions."
                     else: return
            else:
                pos_block = "\n".join(positions)
                msg = f"**Nexus Credit Status ({reason})**\n{pos_block}"
            
            payload = {"content": msg}
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                 async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                     if resp.status in [200, 204]:
                         self.log_msg(f"Status Announce Sent ({reason})")
                     else:
                         self.log_msg(f"Discord Fail: {resp.status}")
        except Exception as e:
            self.log_msg(f"Announce Error: {e}")

    async def active_quote_loop(self):
        """Polls for live spread price every 30s to prevent blind execution."""
        while True:
            if self.selected_spread:
                try:
                    short_sym = self.selected_spread["short_sym"]
                    long_sym = self.selected_spread["long_sym"]
                    
                    ctx = zmq.asyncio.Context()
                    sock = ctx.socket(zmq.REQ)
                    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
                    
                    payload = {"cmd": "GET_MULTI_QUOTE", "symbols": [short_sym, long_sym]}
                    await sock.send_json(payload)
                    
                    if await sock.poll(3000):
                        reply = await sock.recv_json()
                        if reply.get("status") == "ok":
                            quotes = reply.get("quotes", {})
                            
                            qs = quotes.get(short_sym)
                            ql = quotes.get(long_sym)
                            
                            if qs and ql:
                                # Calculate Natural Spread Price
                                # Credit Spread (Sell): Bid Short - Ask Long
                                # Debit Spread (Buy): Ask Short - Bid Long
                                
                                # Default to assuming "SELL" side selected in UI?
                                # Ideally we check logic, but let's calculate the "Mid/Mark" or specifically the actionable price.
                                # Let's show both? Or just the one for the default action (Credit).
                                
                                # Credit: Bid Short - Ask Long
                                cred_price = qs["Bid"] - ql["Ask"]
                                
                                # Use Live Credit
                                self.query_one("#lbl_credit").update(f"${cred_price * 100:.2f} ⚡")
                                
                                # Update Risk
                                width = abs(self.selected_spread["short_strike"] - self.selected_spread["long_strike"])
                                risk = (width - cred_price) * 100 * int(self.query_one("#qty_input").value or 1)
                                equity = self.account_metrics.get("equity", 1)
                                risk_pct = (risk / equity * 100) if equity > 0 else 0
                                
                                self.query_one("#lbl_risk").update(f"${risk:.2f} ({risk_pct:.1f}%) ⚡")
                                
                                # Update Yield
                                yld = (cred_price / width * 100) if width > 0 else 0
                                y_style = "bold red"
                                if yld > 30: y_style = "bold green"
                                elif yld >= 20: y_style = "bold yellow"
                                self.query_one("#lbl_yield").update(f"{yld:.1f}% ⚡")
                                self.query_one("#lbl_yield").styles.color = "green" if yld > 30 else ("yellow" if yld >= 20 else "red")

                    sock.close()
                except Exception as e: 
                     # self.log_msg(f"Quote Error: {e}") # Don't spam log
                     pass
            
            await asyncio.sleep(30)

    async def force_refresh_loop(self):
        """Actively polls for positions for reliability."""
        while True:
            await self.refresh_positions_rpc()
            await asyncio.sleep(5)

    async def refresh_positions_rpc(self):
        try:
            ctx = zmq.asyncio.Context()
            sock = ctx.socket(zmq.REQ)
            sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
            await sock.send_json({"cmd": "GET_POSITIONS"})
            if await sock.poll(2000):
                reply = await sock.recv_json()
                if reply.get("status") == "ok":
                    positions = reply.get("positions", [])
                    self.update_positions(positions)
                    if len(positions) > 0: self.log_msg(f"Refreshed {len(positions)} positions via RPC.")
            else:
                self.log_msg("RPC Refresh Timeout (No Reply)")
            sock.close()
        except Exception as e:
            self.log_msg(f"RPC Refresh Fail: {e}")

    def log_msg(self, msg):
        try:
            t = datetime.datetime.now().strftime("%H:%M:%S")
            # Write to UI
            try: self.query_one("#activity_log", Log).write(f"[{t}] {msg}")
            except: pass
            
            # Write to Disk [DIAGNOSTIC]
            try:
                with open("logs/spreads_debug.log", "a") as f:
                    f.write(f"[{t}] {msg}\n")
            except: pass
        except: pass

    async def market_data_loop(self):
        while True:
            try:
                topic, msg = await self.sub_sock.recv_multipart()
                import json
                data = json.loads(msg)
                if "Last" in data:
                    price = float(data["Last"])
                    self.current_spy_price = price
                    self.query_one("#spy_price_display").update(f"SPY: {price:.2f}")
            except: pass

    def fetch_last_known_price(self):
        """Fallback: Read last known price from JSON if stream is silent (Market Closed)"""
        try:
             import json
             # Try nexus_spy_profile.json first
             try:
                 with open("nexus_spy_profile.json", "r") as f:
                     data = json.load(f)
                     if "current_price" in data:
                         p = float(data["current_price"])
                         self.current_spy_price = p
                         self.query_one("#spy_price_display").update(f"SPY: {p:.2f} (C)")
                         self.log_msg(f"Loaded Closed Price: ${p:.2f}")
                         return
             except: pass
        except: pass

    async def account_data_loop(self):
        while True:
            try:
                topic, msg = await self.acct_sock.recv_multipart()

                import json
                data = json.loads(msg)
                positions = data.get("positions", [])
                
                # Update Account Metrics
                # TS API returns 'Equity' in balances, but we need to calculate P/L and Exp from positions if not provided
                # Actually, ts_nexus.py sends: {"total_account_value": equity, "positions": positions}
                # It does NOT send 'unrealized_pnl' or 'value_of_open_positions' directly in the root json.
                # We must calculate them from positions!
                
                eq = float(data.get("total_account_value", 0))
                self.account_metrics["equity"] = eq 
                
                pl = sum([float(p.get("UnrealizedProfitLoss", 0)) for p in positions])
                exp = sum([float(p.get("MarketValue", 0)) for p in positions])
                
                # Calculate Percentages
                pl_pct = (pl / eq * 100) if eq != 0 else 0.0
                exp_pct = (exp / eq * 100) if eq != 0 else 0.0
                
                self.query_one("#acct_display").update(f"P/L: ${pl:.0f} ({pl_pct:+.1f}%) | EXP: ${exp/1000:.1f}K ({exp_pct:.1f}%)")
                
                self.update_positions(positions)
            except: pass

    def update_positions(self, positions):
        # Phase 20: Credit Sniper Alignment (Debit Layout)
        # Columns: STRATEGY, STRIKES, DTE, QTY, P/L OPEN, EXPOSURE, STOP, PT
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        self.managed_spreads = {}
        processed_syms = set()
        import datetime, re
        
        # Show ALL spreads (Debit + Credit)
        # Credit Logic: Credit Put/Call.
        # Debit Logic: we want to close them too.
        # How do we differentiate? `update_positions` logic below was tailored for Credit groupings.
        # We need to adapt it or ensure it handles Debits correctly if they appear in `positions`.
        # The logic groups by expiry -> calls/puts.
        # Then finds short/long pairs.
        # It assumes Credit logical pairing (Short < Long for Put, Short < Long for Call? No).
        # Credit Put: Short < Long.
        # Debit Put: Long < Short? (Buy Put High, Sell Put Low).
        # We need to detect the pairings generically.
        
        def get_k(s):
            m = re.search(r'[CP]([\d.]+)$', s)
            return float(m.group(1)) if m else 0

        # 1. Group by Expiry
        expiry_groups = {}
        for p in positions:
            sym = p.get("Symbol", "")
            try:
                parts = sym.split(' ')
                if len(parts) > 1:
                    code = parts[1]
                    expiry = code[:6]
                    if expiry not in expiry_groups: expiry_groups[expiry] = []
                    expiry_groups[expiry].append(p)
            except: pass
            
        for expiry, group in expiry_groups.items():
            try:
                exp_dt = datetime.datetime.strptime(expiry, "%y%m%d")
                dte_val = (exp_dt - datetime.datetime.now()).days
                dte_str = f"{dte_val}d"
            except: dte_str = "-d"
            
            calls = [x for x in group if "C" in x.get("Symbol").split(' ')[1]]
            puts = [x for x in group if "P" in x.get("Symbol").split(' ')[1]]
            
            # --- CREDIT PUTS (Bull Put) ---
            # Short Put > Long Put. Short has Negative Qty. Long has Positive Qty.
            short_puts = [p for p in puts if int(p.get("Quantity", 0)) < 0]
            long_puts = [p for p in puts if int(p.get("Quantity", 0)) > 0]
            
            for s in short_puts:
                s_sym = s.get("Symbol")
                if s_sym in processed_syms: continue
                k_short = get_k(s_sym)
                
                # Find matching Long (Lower Strike)
                match = None
                for l in long_puts:
                    if l.get("Symbol") in processed_syms: continue
                    k_long = get_k(l.get("Symbol"))
                    if k_long < k_short: # Bull Put Condition
                        match = l
                        break
                
                if match:
                    qty = abs(int(s.get("Quantity")))
                    pl = float(s.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(s.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    
                    # Credit Stats
                    # Check Backend for Authoritative Stop
                    backend_data = self.backend_spreads.get(s_sym, {})
                    backend_stop = backend_data.get("stop_trigger", 0)
                    
                    if backend_stop > 0:
                        stop_lvl = backend_stop
                    else:
                        stop_lvl = k_short + 0.5 
                    
                    # Exposure
                    equity = self.account_metrics.get("equity", 1)
                    width = abs(k_short - k_long)
                    margin = width * 100 * qty
                    exp_pct = (margin / equity * 100) if equity > 0 else 0
                    
                    # P/L %
                    cost_basis = val - pl
                    pl_pct = 0.0
                    if abs(cost_basis) > 0.001:
                        pl_pct = (pl / abs(cost_basis)) * 100
                        
                    pl_style = "bold green" if pl > 0 else "bold red"
                    
                    table.add_row(
                        "CREDIT PUT", f"{k_short}/{k_long}", dte_str, str(qty),
                        Text(f"{pl_pct:+.1f}%", style=pl_style),
                        f"{exp_pct:.1f}% (Marg)",
                        f"{stop_lvl:.2f}",
                        "50% Max",
                        key=f"SPREAD|{s_sym}|{match.get('Symbol')}"
                    )
                    
                    processed_syms.add(s_sym)
                    processed_syms.add(match.get("Symbol"))
                    
                    # Sync
                    self.managed_spreads[s_sym] = {
                        "short_sym": s_sym, "long_sym": match.get("Symbol"),
                        "short_strike": k_short, "long_strike": k_long,
                        "qty": qty, "type": "PUT", "credit": True
                    }

                
            # --- CREDIT CALLS (Bear Call) ---
            # Short Call < Long Call. Short has Negative Qty. Long has Positive.
            short_calls = [c for c in calls if int(c.get("Quantity", 0)) < 0]
            long_calls = [c for c in calls if int(c.get("Quantity", 0)) > 0]
            
            for s in short_calls:
                s_sym = s.get("Symbol")
                if s_sym in processed_syms: continue
                k_short = get_k(s_sym)
                
                # Find matching Long (Higher Strike)
                match = None
                for l in long_calls:
                    if l.get("Symbol") in processed_syms: continue
                    k_long = get_k(l.get("Symbol"))
                    if k_long > k_short: # Bear Call Condition (Short < Long)
                        match = l
                        break
                
                if match:
                    qty = abs(int(s.get("Quantity")))
                    pl = float(s.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(s.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    
                    # Stop: 0.5 ITM Safety Buffer
                    # Credit Call: Lose if price rises.
                    # Stop Trigger = Short Strike - 0.5 (Exit before it rises fully to strike)
                    
                    # Check Backend for Authoritative Stop
                    backend_data = self.backend_spreads.get(s_sym, {})
                    backend_stop = backend_data.get("stop_trigger", 0)
                    
                    if backend_stop > 0:
                        stop_lvl = backend_stop
                    else:
                        stop_lvl = k_short - 0.5
                    
                    # Exposure
                    equity = self.account_metrics.get("equity", 1)
                    width = abs(k_long - k_short)
                    margin = width * 100 * qty
                    exp_pct = (margin / equity * 100) if equity > 0 else 0
                    
                    # P/L %
                    cost_basis = val - pl
                    pl_pct = 0.0
                    if abs(cost_basis) > 0.001:
                         pl_pct = (pl / abs(cost_basis)) * 100

                    pl_style = "bold green" if pl > 0 else "bold red"
                    
                    table.add_row(
                        "CREDIT CALL", f"{k_short}/{k_long}", dte_str, str(qty),
                        Text(f"{pl_pct:+.1f}%", style=pl_style),
                        f"{exp_pct:.1f}% (Marg)",
                        f"{stop_lvl:.2f}",
                        "50% Max",
                        key=f"SPREAD|{s_sym}|{match.get('Symbol')}"
                    )
                    
                    processed_syms.add(s_sym)
                    processed_syms.add(match.get("Symbol"))
                    
                    self.managed_spreads[s_sym] = {
                        "short_sym": s_sym, "long_sym": match.get("Symbol"),
                        "short_strike": k_short, "long_strike": k_long,
                        "qty": qty, "type": "CALL", "credit": True
                    }




        #         pl = float(p.get("UnrealizedProfitLoss", 0))
        #         val = float(p.get("MarketValue", 0))
        #         table.add_row(f"❓ {sym}", str(qty), f"${pl:.2f}", f"${val:.2f}", key=f"UNMANAGED|{sym}")
        #         processed_syms.add(sym)

    async def fetch_managed_spreads_loop(self):
        while True:
            try:
                ctx = zmq.asyncio.Context()
                sock = ctx.socket(zmq.REQ)
                sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
                
                await sock.send_json({"cmd": "GET_MANAGED_SPREADS"})
                if await sock.poll(2000):
                    reply = await sock.recv_json()
                    if reply.get("status") == "ok":
                        # Parse list of dicts into dict of short_sym -> details
                        spreads_list = reply.get("spreads", [])
                        # Store in separate backend dict to avoid overwrite by update_positions
                        self.backend_spreads = {s["short_sym"]: s for s in spreads_list if "short_sym" in s}
                sock.close()
            except: pass
            await asyncio.sleep(2)

    async def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "fetch_btn":
            await self.fetch_chain()
        elif event.button.id == "execute_btn":
            await self.execute_trade(side="SELL")
        elif event.button.id == "execute_buy_btn":
            await self.execute_trade(side="BUY")
        elif event.button.id == "refresh_btn":
            await self.refresh_positions_rpc()
            self.log_msg("Manual Refresh Triggered")
        elif event.button.id == "cancel_btn":
            await self.panic_close()

    async def fetch_chain(self):
        btn = self.query_one("#fetch_btn")
        btn.disabled = True
        btn.label = "FETCHING..."
        self.log_msg("Fetching Option Chain...")
        
        type_ = self.query_one("#type_select").value
        strike = self.query_one("#strike_input").value
        width = self.query_one("#width_input").value
        
        if not strike or not width:
            self.log_msg("Error: Missing Strike or Width")
            btn.disabled = False; btn.label = "FETCH CHAIN"
            return

        payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "strike": strike, "width": width, "type": type_}
        
        try:
            # [FIX] Backend is slow for GET_CHAIN. Increase timeout to 45s to match nexus_debit.py
            reply = await self.robust_send(payload, timeout_ms=45000)
            if reply and reply.get("status") == "ok":
                # IV/IVR Logic
                iv = reply.get("iv", 0)
                ivr = reply.get("ivr", 0)
                price = reply.get("price", 0.0)

                # Update Internal Price
                if price > 0:
                    self.current_spy_price = price
                    try: self.query_one("#spy_price_display").update(f"SPY: {price:.2f}")
                    except: pass

                # Update Header - INVERTED Logic for Credit
                # High IVR = GOOD (Green)
                # Low IVR = BAD (Red)
                color = "white"
                if ivr > 50: color = "bold green"
                elif ivr < 30: color = "bold red"
                
                iv_txt = f"[{color}]IV: {iv:.1f}% | IVR: {ivr:.0f}[/]"
                try: self.query_one("#lbl_iv_status", Label).update(iv_txt)
                except: pass

                if ivr < 30:
                    self.log_msg(f"⚠️ LOW VOLATILITY (IVR {ivr}). CREDIT SPREADS RISKY (Low Premium).")

                self.populate_chain(reply.get("data", []), ivr)
                self.log_msg(f"Fetched {len(reply.get('data', []))} spreads.")
            elif reply:
                self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")
            
        btn.disabled = False
        btn.label = "FETCH CHAIN"

    def populate_chain(self, data, ivr=0.0):
        table = self.query_one("#chain_table", DataTable)
        table.clear()

        cur_price = self.current_spy_price
        if cur_price <= 0: cur_price = 0.01

        # Prob Adj Logic (INVERTED)
        if ivr > 50:
            prob_txt = "[bold green]Rich (High IV)[/]"
        elif ivr < 30:
            prob_txt = "[bold red]Cheap (Low IV)[/]"
        else:
            prob_txt = "Neutral"

        for item in data:
            try:
                # Basic Values
                credit = float(item.get('credit', 0))
                width = abs(float(item.get('short', 0)) - float(item.get('long', 0)))
                risk = width - credit
                
                if risk <= 0: risk = 0.01 # Avoid div/0

                # Max ROC % (Credit / Risk)
                max_roc = (credit / risk) * 100 if risk > 0 else 0
                
                # B/E
                be = float(item.get('breakeven', 0))

                # % TO B/E Calculation
                # Credit Call (Bear): BE is ABOVE price. Dist = BE - Price.
                # Credit Put (Bull): BE is BELOW price. Dist = Price - BE.
                # If Price is past BE (ITM/Loss), dist is negative.
                
                dist_pct = 0.0
                if cur_price > 1.0:
                    if item.get("short") > item.get("long"): 
                        # Bull Put (Short Higher? Wait. Bull Put = Short Low Put, Long Lower Put. 
                        # Short 500P, Long 495P. Short > Long? YES.
                        # BE = Short - Credit.
                        # We want Price > BE.
                        # Dist = (Price - BE) / Price
                        dist_pct = ((cur_price - be) / cur_price) * 100
                    else:
                        # Bear Call (Short Low Call, Long High Call. Wait. Bear Call = Short Low, Long High?
                        # Short 500C, Long 505C. Short < Long? YES.
                        # BE = Short + Credit.
                        # We want Price < BE.
                        # Dist = (BE - cur_price) / cur_price
                         dist_pct = ((be - cur_price) / cur_price) * 100
                
                # Color for Dist
                if dist_pct < 0: dist_style = "[bold red]" # ITM / Fails
                elif dist_pct < 1.0: dist_style = "[bold yellow]" # Close
                else: dist_style = "[bold green]" # Safe

                dist_str = f"{dist_style}{dist_pct:.2f}%[/]"

                roc_style = "bold green" if max_roc > 20 else "white"
                
                # Delta (Short) - Approximation or Fetch?
                # Nexus Chain data usually puts Delta in 'delta' key?
                # If not available, use "N/A"
                delta = item.get("delta", "N/A")

                row = [
                    item["expiry"], str(item["dte"]), 
                    f"{item['short']:.1f}", f"{item['long']:.1f}",
                    f"${credit:.2f}", 
                    f"${risk:.2f}",
                    Text(f"{max_roc:.1f}%", style=roc_style),
                    prob_txt
                ]
                key = f"{item['short_sym']}|{item['long_sym']}|{credit}|{item['short']}|{item['long']}"
                table.add_row(*row, key=key)
            except Exception as e:
                pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        if event.data_table.id == "chain_table":
            self.query_one("#execute_btn").disabled = False
            self.query_one("#execute_buy_btn").disabled = False
            self.query_one("#cancel_btn").disabled = True 
            
            key = event.row_key.value
            parts = key.split("|")
            self.selected_spread = {
                "short_sym": parts[0], "long_sym": parts[1],
                "credit": float(parts[2]), "short_strike": float(parts[3]), "long_strike": float(parts[4])
            }
            
            # Update Sidebar
            self.query_one("#lbl_spread").update(f"{parts[3]}/{parts[4]}")
            self.query_one("#lbl_credit").update(f"${parts[2]}")
            
            # Update Yield in Sidebar
            width = abs(float(parts[3]) - float(parts[4]))
            credit = float(parts[2])
            yield_pct = (credit / width * 100) if width > 0 else 0
            y_style = "bold red"
            if yield_pct > 30: y_style = "bold green"
            elif yield_pct >= 20: y_style = "bold yellow"
            
            self.query_one("#lbl_yield").update(f"{yield_pct:.1f}%")
            self.query_one("#lbl_yield").styles.color = "green" if yield_pct > 30 else ("yellow" if yield_pct >= 20 else "red")
            
            self.query_one("#lbl_risk").update(f"${float(parts[4]) - float(parts[3]) if float(parts[3]) < float(parts[4]) else float(parts[3]) - float(parts[4])}")
            
            # Calculate Stop Trigger (Underlying Price)
            # FIXED: User Requested 0.5 offset from Short Strike (Defensive)
            # Old Logic: Half Width (Too wide/tight depending on width)
            
            is_put = "P" in parts[0]
            if is_put:
                # Bull Put: We lose if price drops (Below Short).
                # Stop = Short Strike + 0.5 (Stop before full breach)
                stop_price = self.selected_spread["short_strike"] + 0.5
            else:
                # Bear Call: We lose if price rises (Above Short).
                # Stop = Short Strike - 0.5 (Stop before full breach)
                stop_price = self.selected_spread["short_strike"] - 0.5
                
            self.selected_spread["stop_trigger"] = stop_price
            self.query_one("#lbl_stop").update(f"{stop_price:.2f}")
            
            # Initial Risk Calc
            self.calculate_risk()
            
        elif event.data_table.id == "positions_table":
            # Handle Position Selection for Panic Close
            key = event.row_key.value
            if key and key.startswith("SPREAD|"):
                parts = key.split("|")
                short_sym = parts[1]
                long_sym = parts[2]
                self.selected_spread = {"short_sym": short_sym, "long_sym": long_sym}
                
                self.query_one("#cancel_btn").disabled = False
                self.query_one("#execute_btn").disabled = True
                self.query_one("#execute_buy_btn").disabled = True
                
                self.query_one("#lbl_spread").update(f"{short_sym.split(' ')[-1]}/{long_sym.split(' ')[-1]}")
                self.query_one("#lbl_credit").update("OPEN")
                self.query_one("#lbl_risk").update("OPEN")
                self.query_one("#lbl_stop").update("OPEN")

    @on(Input.Changed, "#qty_input")
    def on_qty_change(self, event: Input.Changed):
        self.calculate_risk()

    def calculate_risk(self):
        if not self.selected_spread: return
        
        try:
            qty = int(self.query_one("#qty_input").value)
        except: qty = 1
        
        # Risk per Spread
        # Credit Spread Risk = Width - Credit
        # Debit Spread Risk = Debit Paid (which is the "Credit" field but negative? No, fetch_chain returns positive credit for credit spreads)
        # Wait, fetch_chain logic:
        # Credit = Bid Short - Ask Long.
        # If Credit > 0: Credit Spread. Risk = Width - Credit.
        # If Credit < 0: Debit Spread. Cost = -Credit. Risk = Cost.
        
        # However, fetch_chain calculates 'risk' field assuming Credit Spread logic?
        # Let's check fetch_chain in ts_nexus.py...
        # It calculates: credit = bid_short - ask_long. risk = width - credit.
        # If it's a Debit Spread (e.g. Bull Call), Short is Lower Strike (Buy), Long is Higher (Sell).
        # Bid Short (Buy) - Ask Long (Sell)? No.
        # Debit Spread: Buy Short (Ask), Sell Long (Bid).
        # Cost = Ask Short - Bid Long.
        # fetch_chain logic might be flawed for Debit if it assumes Credit logic.
        # But for now, let's rely on the 'risk' value from the table row if possible, or recalculate.
        # The table row has "RISK" column.
        # self.selected_spread has "credit", "short_strike", "long_strike".
        
        # Let's assume Credit Spread logic for now as that's the primary use case.
        # Risk Per Contract = Width - Credit
        width = abs(self.selected_spread["short_strike"] - self.selected_spread["long_strike"])
        credit = self.selected_spread["credit"]
        
        # If Credit is negative, it's a Debit.
        # If Credit is negative, it's a Debit.
        if credit < 0:
             risk_per_share = abs(credit)
        else:
             risk_per_share = width - credit
             
        total_risk = risk_per_share * 100 * qty
        
        # Calculate Total Credit (Credit * 100 * Qty)
        total_credit = credit * 100 * qty
        self.query_one("#lbl_credit").update(f"${total_credit:.2f}")
        
        # Calculate % of Account
        equity = self.account_metrics.get("equity", 0)
        risk_pct = (total_risk / equity * 100) if equity > 0 else 0.0
        
        self.query_one("#lbl_risk").update(f"${total_risk:.2f} ({risk_pct:.1f}%)")

    async def execute_trade(self, side="SELL"):
        if not self.selected_spread: return
        try:
            qty = int(self.query_one("#qty_input").value)
        except: 
            self.log_msg("Error: Invalid Qty")
            return
            
        self.log_msg(f"Executing Trade ({side} TO OPEN) Qty:{qty}...")
        
        payload = {
            "cmd": "EXECUTE_SPREAD",
            "short_sym": self.selected_spread["short_sym"],
            "long_sym": self.selected_spread["long_sym"],
            "qty": qty,
            "price": self.selected_spread["credit"], # Used for Profit Calc
            "stop_trigger": self.selected_spread["stop_trigger"],
            "order_type": "MARKET", # Changed to MARKET to ensure fill
            "side": side
        }
        
        try:
            # [FIX] Use robust_send to prevent socket hang on previous timeout
            reply = await self.robust_send(payload)
            if reply and reply.get("status") == "ok":
                self.log_msg(f"Order Sent! ID: {reply.get('order_id')}")
            elif reply:
                self.log_msg(f"Exec Error: {reply.get('msg')}")
            else:
                 self.log_msg("Exec Fail: No Reply (Timeout)")
        except Exception as e:
            self.log_msg(f"Exec Exception: {e}")

    @on(DataTable.RowSelected, "#positions_table")
    def on_pos_selected(self, event: DataTable.RowSelected):
        """Captures selection for potential closing."""
        row_key = event.row_key
        row = self.query_one("#positions_table").get_row(row_key)
        # Row: STRATEGY, STRIKES, DTE, QTY...
        # We need to map back to managed_spreads using Strikes/Strategy?
        # Or easier: store sym in row_key?
        # Textual RowKey is generic.
        # It's better if we stored the 'short_sym' in the managed_spreads keyed by something unique or just search.
        
        # Strategy: "CREDIT PUT", Strikes: "700/690"
        strategy = str(row[0])
        strikes = str(row[1])
        qty = str(row[3])
        
        self.log_msg(f"Create Action: Selected {strategy} {strikes}")
        
        # [FIX] Explicitly populate selected_spread from Row Key for Fallback Logic
        # RowKey Format: SPREAD|short_sym|long_sym
        if row_key and "|" in row_key.value:
            parts = row_key.value.split("|")
            if len(parts) >= 3:
                self.selected_spread = {
                    "short_sym": parts[1],
                    "long_sym": parts[2],
                    "quantity": qty # Store display quantity
                }
                self.log_msg(f"✅ Data Captured: {parts[1]}/{parts[2]}")
        
        # Activate Panic Close Button
        self.query_one("#cancel_btn").disabled = False
        
        # Store for logic
        self.selected_position_row = {
            "strategy": strategy,
            "strikes": strikes,
            "qty": qty
        }

    async def panic_close(self):
        """Trigger Confirmation Modal instead of instant close."""
        if not hasattr(self, 'selected_position_row') or not self.selected_position_row:
            self.log_msg("No Position Selected!")
            return

        p = self.selected_position_row
        msg = f"⚠ CONFIRM CLOSE ⚠\n\n{p['strategy']} {p['strikes']} (x{p['qty']})\n\nAction: MARKET ORDER (Immediate Fill)"
        
        def do_close():
            self.run_worker(self.execute_close_logic(p))
            
        self.push_screen(CloseConfirmModal(msg, do_close))

    async def execute_close_logic(self, p):
        """Determines side and sends close command."""
        self.log_msg(f"Closing {p['strategy']}...")
        
        # We need to find the symbols again from `managed_spreads`.
        # Strategy "CREDIT PUT" means we SOLD to Open. We need to BUY to Close.
        # "DEBIT CALL" means we BOUGHT to Open. We need to SELL to Close.
        
        # How to match `p` back to `managed_spreads`?
        # Iterate managed spreads and match 'strikes' and 'type'?
        target_spread = None
        target_k = p['strikes'].split('/') # "700/650"
        try:
             k1 = float(target_k[0])
             k2 = float(target_k[1])
        except: return 
        
        for sym, data in self.managed_spreads.items():
            # Check Strikes
            if abs(data['short_strike'] - k1) < 0.1 and abs(data['long_strike'] - k2) < 0.1:
                target_spread = data
                break
        
        if not target_spread:
            # Fallback for UNMANAGED/ORPHANED spreads
            # The 'selected_spread' attribute is populated by 'on_pos_selected' from the row key
            # which contains the symbols!
            if self.selected_spread and "short_sym" in self.selected_spread:
                self.log_msg("⚠️ Using Unmanaged Symbols (Fallback)...")
                target_spread = self.selected_spread
            else:
                self.log_msg("Error: Could not find spread symbols for selection.")
                return

        # Determine logic
        # If "CREDIT": We are Short. Close = Buy.
        # If "DEBIT": We are Long. Close = Sell.
        
        # [CRITICAL FIX] Use CLOSE_SPREAD command.
        # CLOSE_SPREAD in ts_nexus.py expects the ORIGINAL SIDE (e.g. "SELL" for Credit Spreads).
        # It handles the inversion (BuyToClose) internally.
        # Do NOT invert the side here.
        
        # Original Side is in target_spread['type']? No, 'side' key or implied by strategy.
        # managed_spreads has 'credit': True/False.
        # If credit=True, side="SELL". If credit=False, side="BUY".
        
        is_credit = target_spread.get("credit", False)
        # Fallback check if 'side' key exists (from registry)
        if "side" in target_spread:
             is_credit = target_spread["side"] == "SELL"
             
        original_side = "SELL" if is_credit else "BUY"
        
        self.log_msg(f"Panic Close: {target_spread.get('short_sym')} (OrigSide: {original_side})")
        
        payload = {
            "cmd": "CLOSE_SPREAD", # [FIX] Use dedicated Close command
            "short_sym": target_spread['short_sym'],
            "long_sym": target_spread['long_sym'],
            "qty": int(p['qty']),
            "side": original_side # [FIX] Pass original side, backend inverts it
        }
        
        try:
            # [FIX] Use robust_send for Close logic too
            reply = await self.robust_send(payload)
            if reply and reply.get("status") == "ok":
                self.log_msg(f"Close Order Sent! ID: {reply.get('order_id', 'N/A')}")
            elif reply:
                self.log_msg(f"Error: {reply.get('msg')}")
            else:
                 self.log_msg("Close Fail: No Reply (Timeout)")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")

if __name__ == "__main__":
    SpreadSniperApp().run()
