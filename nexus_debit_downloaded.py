import sys
import zmq
import zmq.asyncio
import asyncio
import datetime
try:
    import pytz
except ImportError:
    pytz = None

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

# --- STRATEGY CONSTANTS ---
TARGET_DELTA_LONG = 0.70  # The "Stock Replacement" Anchor
TARGET_DELTA_SHORT = 0.30 # The Financing Leg
DEFAULT_ROI_TARGET = 0.58 # +58% Profit Target
DEFAULT_STOP_PCT = 0.03   # -3% Drop in Underlying (SPY)

class DebitSniperApp(App):
    CSS = """
    Screen { background: #0d1117; }
    
    /* HEADER */
    #control_bar {
        dock: top;
        height: 3;
        background: #161b22;
        border-bottom: solid #1f6feb; /* Blue for Debit */
        padding: 0 1;
        align: left middle;
    }
    
    .control-item { margin-right: 2; }
    .control-item-right { margin-left: 4; color: #58a6ff; text-style: bold; content-align: right middle; width: 1fr; }
    #type_select { width: 12; }
    #strike_input { width: 12; }
    #width_input { width: 12; }
    #fetch_btn { background: #1f6feb; color: #fff; text-style: bold; border: none; }
    
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
        border: solid #30363d;
        background: #0d1117;
    }
    
    /* RIGHT PANE: EXECUTION */
    #exec_container {
        row-span: 2;
        column-span: 1;
        border-left: solid #1f6feb;
        background: #161b22;
        padding: 1;
    }
    

    /* BOTTOM PANE: POSITIONS & LOG */
    #bottom_container {
        row-span: 1;
        column-span: 1;
        layout: vertical;
        /* Removed grid-columns */
    }
    
    #positions_table {
        border-top: solid #444;
        height: 1fr;
        width: 100%;
    }
    
    #activity_log {
        border-top: solid #444;
        height: 1fr;
        width: 100%;
        background: #000;
        overflow-x: auto;
    }

        /* EXECUTION WIDGETS */
    .exec-label { color: #8b949e; margin-top: 1; }
    .exec-value { color: #fff; text-style: bold; margin-bottom: 1; }
    
    #execute_btn {
        width: 100%;
        background: #238636; /* Green for Buy */
        color: white;
        text-style: bold;
        margin-top: 2;
        height: 3;
    }
    
    #cancel_btn {
        width: 100%;
        background: #da3633;
        color: white;
        text-style: bold;
        margin-top: 1;
    }
    
    #spy_price_display {
        background: #161b22;
        color: #3fb950;
        text-align: center;
        text-style: bold;
        padding: 1;
        border: solid #3fb950;
        margin-bottom: 2;
    }
    
    /* MODAL */
    .modal-dialog {
        padding: 2;
        background: #161b22;
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
    #btn_cancel { margin-left: 2; background: #30363d; }
    """

    def __init__(self):
        super().__init__()
        # ZMQ SETUP
        self.zmq_ctx = zmq.asyncio.Context()
        self.req_sock = self.zmq_ctx.socket(zmq.REQ)
        self.req_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
        
        self.sub_sock = self.zmq_ctx.socket(zmq.SUB)
        self.sub_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_MARKET}")
        self.sub_sock.subscribe(b"SPY")
        
        self.acct_sock = self.zmq_ctx.socket(zmq.SUB)
        self.acct_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_ACCOUNT}")
        self.acct_sock.subscribe(b"A")

        # STATE
        self.current_spy_price = 0.0
        self.selected_spread = None
        self.managed_spreads = {} 
        self.account_metrics = {"equity": 0, "pl": 0}
        
        # HYBRID MANAGER CONFIG
        self.auto_exit_enabled = True

    def compose(self) -> ComposeResult:
        with Horizontal(id="control_bar"):
            yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")
            yield Label("IV: --% | IVR: --", id="lbl_iv_status", classes="control-item")
            yield Select.from_values(["CALL", "PUT"], allow_blank=False, value="CALL", id="type_select", classes="control-item")
            yield Input(placeholder="Strike", id="strike_input", classes="control-item")
            yield Input(placeholder="Width", value="30", id="width_input", classes="control-item")
            yield Button("SCAN SETUP", id="fetch_btn", classes="control-item")
            yield Button("↻ REFRESH", id="refresh_btn", classes="control-item")
            yield Static("ACCT: ---", id="acct_display", classes="control-item-right")

        with Grid(id="main_grid"):
            # Option Chain
            with Vertical(id="chain_container"):
                yield Label(" OPTION CHAIN (Target: Delta 0.70)", classes="panel-header")
                yield DataTable(id="chain_table")
            
            # Execution Sidebar
            with Vertical(id="exec_container"):
                yield Static("SPY: ---", id="spy_price_display")
                
                yield Label("SELECTED SETUP:", classes="exec-label")
                yield Static("-", id="lbl_spread", classes="exec-value")
                
                yield Label("DEBIT COST:", classes="exec-label")
                yield Static("-", id="lbl_debit", classes="exec-value")
                
                yield Label("TGT PROFIT (50%):", classes="exec-label")
                yield Static("-", id="lbl_profit", classes="exec-value")
                
                yield Label("MAX ROC %:", classes="exec-label")
                yield Static("-", id="lbl_roc", classes="exec-value")
                
                yield Label("STOP TRIGGER (SPY Price):", classes="exec-label")
                yield Static("-", id="lbl_stop_trigger", classes="exec-value")
                
                yield Label("LOT SIZE:", classes="exec-label")
                yield Input(value="1", id="qty_input", classes="control-item")
                
                yield Button("BUY TO OPEN", id="execute_btn", disabled=True)
                yield Button("CLOSE SELECTED", id="cancel_btn", disabled=True)

            # Bottom Panel (VERTICAL STACK)
            with Vertical(id="bottom_container"):
                with Vertical():
                    yield Label(" ACTIVE POSITIONS", classes="panel-header")
                    yield DataTable(id="positions_table") # Full Width
                with Vertical():
                    yield Label(" SYSTEM LOG", classes="panel-header")
                    yield Log(id="activity_log") # Full Width
    
    def update_positions(self, positions):
        # Phase 10 Logic: Exposure %, ARMED PT, Data Sync, Guarded Logic
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        # Reset Managed Spreads Sync
        self.managed_spreads = {}
        processed_syms = set()
        
        import datetime
        
        # 1. GROUP BY EXPIRY
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
            
        def get_k(s):
            import re
            m = re.search(r'[CP]([\d.]+)$', s)
            return float(m.group(1)) if m else 0
        for expiry, group in expiry_groups.items():
            try:
                exp_dt = datetime.datetime.strptime(expiry, "%y%m%d")
                dte_val = (exp_dt - datetime.datetime.now()).days
                dte_str = f"{dte_val}d"
            except: dte_str = "-d"
            calls = [x for x in group if "C" in x.get("Symbol").split(' ')[1]]
            puts = [x for x in group if "P" in x.get("Symbol").split(' ')[1]]
            
            # --- CALLS ---
            long_calls = [c for c in calls if int(c.get("Quantity", 0)) > 0]
            short_calls = [c for c in calls if int(c.get("Quantity", 0)) < 0]
            
            for l in long_calls:
                l_sym = l.get("Symbol")
                if l_sym in processed_syms: continue
                k_long = get_k(l_sym)
                
                match = None
                for s in short_calls:
                    if s.get("Symbol") in processed_syms: continue
                    k_short = get_k(s.get("Symbol"))
                    if k_short > k_long: # Bull Call Spread
                        match = s
                        break
                
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    cost = val - pl
                    if cost < 0.01: cost = 0.01 
                    roi = (pl / cost) * 100
                    pl_str = f"{roi:+.1f}%"
                    # LOGIC: 1% Stop
                    stop_lvl = k_long * 0.99
                    
                    # EXPOSURE (Current Value / Equity)
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (val / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"
                    strikes_str = f"{k_long}/{k_short}"
                    table.add_row(
                        "DEBIT CALL", strikes_str, dte_str, str(qty), 
                        Text(pl_str, style="bold green" if pl > 0 else "bold red"), 
                        Text(f"{exposure_pct:.1f}%", style=exp_style),
                        f"{stop_lvl:.2f}", 
                        Text("ARMED", style="bold green")
                    )
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))
                    
                    # DATA SYNC
                    self.managed_spreads[l_sym] = {
                        "long_sym": l_sym, "short_sym": match.get("Symbol"),
                        "long_strike": k_long, "short_strike": k_short,
                        "qty": qty, "avg_price": cost, "is_call": True
                    }
            # --- PUTS ---
            long_puts = [p for p in puts if int(p.get("Quantity", 0)) > 0]
            short_puts = [p for p in puts if int(p.get("Quantity", 0)) < 0]
            
            for l in long_puts:
                l_sym = l.get("Symbol")
                if l_sym in processed_syms: continue
                k_long = get_k(l_sym)
                
                match = None
                for s in short_puts:
                    if s.get("Symbol") in processed_syms: continue
                    k_short = get_k(s.get("Symbol"))
                    if k_short < k_long: # Bear Put Spread? No, Bull Put is Credit. Debit Put is Bearish.
                        # Debit Put: Long Strike > Short Strike? 
                        # Long Put (High Strike) + Short Put (Low Strike).
                        # e.g. Buy 100 Put, Sell 90 Put. k_long (100) > k_short (90).
                        pass
                    # Wait, logic check:
                    # Debit Put Spread: Long ITM/ATM, Short OTM.
                    # Usually Long Strike > Short Strike.
                    # e.g. Long 400P, Short 390P.
                    # Previous code: "if k_short < k_long:" 
                    if k_short < k_long:
                        match = s
                        break
                        
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    cost = val - pl
                    if cost < 0.01: cost = 0.01
                    roi = (pl / cost) * 100
                    pl_str = f"{roi:+.1f}%"
                    
                    stop_lvl = k_long * 1.01
                    
                    # EXPOSURE
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (val / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"
                    
                    strikes_str = f"{k_long}/{k_short}"
                    table.add_row(
                        "DEBIT PUT", strikes_str, dte_str, str(qty), 
                        Text(pl_str, style="bold green" if pl > 0 else "bold red"), 
                        Text(f"{exposure_pct:.1f}%", style=exp_style),
                        f"{stop_lvl:.2f}", 
                        Text("ARMED", style="bold green")
                    )
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))
                    
                    # DATA SYNC
                    self.managed_spreads[l_sym] = {
                        "long_sym": l_sym, "short_sym": match.get("Symbol"),
                        "long_strike": k_long, "short_strike": k_short,
                        "qty": qty, "avg_price": cost, "is_call": False
                    }
    async def account_data_loop(self):
        while True:
            try:
                topic, msg = await self.acct_sock.recv_multipart()
                import json
                data = json.loads(msg)
                positions = data.get("positions", [])
                eq = float(data.get("total_account_value", 0))
                self.account_metrics["equity"] = eq
                pl = sum([float(p.get("UnrealizedProfitLoss", 0)) for p in positions])
                pl_pct = (pl / eq * 100) if eq != 0 else 0.0
                self.query_one("#acct_display").update(f"P/L: ${pl:.0f} ({pl_pct:+.1f}%)")
                self.call_after_refresh(self.update_positions, positions)
            except: pass
            
    async def fetch_managed_spreads_loop(self):
        while True:
            try:
                await self.req_sock.send_json({"cmd": "GET_MANAGED_SPREADS"})
                if await self.req_sock.poll(2000):
                    reply = await self.req_sock.recv_json()
                    if reply.get("status") == "ok":
                        sl = reply.get("spreads", [])
                        self.managed_spreads = {s["short_sym"]: s for s in sl if "short_sym" in s}
            except: pass
            await asyncio.sleep(2)
    
    
    async def status_scheduler_loop(self):
        """Checks time for scheduled status announcements (Open/Close)."""
        while True:
            await asyncio.sleep(60) # Check every minute
            try:
                now_et = datetime.datetime.now(pytz.timezone('US/Eastern'))
                t_str = now_et.strftime("%H:%M")
                
                # Market Open (09:30)
                if t_str == "09:30":
                    await self.announce_status("MARKET_OPEN")
                    await asyncio.sleep(60) # Avoid double trigger
                    
                # Market Close (16:00)
                if t_str == "16:00":
                    await self.announce_status("MARKET_CLOSE")
                    await asyncio.sleep(60)
            except Exception as e:
                self.log_msg(f"Scheduler Error: {e}")

    async def announce_status(self, reason="UPDATE"):
        """Compiles active positions and posts to Discord."""
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            # Gather Managed Spreads
            if self.managed_spreads:
                for sym, data in self.managed_spreads.items():
                    # Format: "Debit Call: SPY 675/705 (3.0% Exp) - ARMED"
                    try:
                        k_long = data.get("long_strike", 0)
                        k_short = data.get("short_strike", 0)
                        is_call = data.get("is_call", True)
                        strat_type = "Debit Call" if is_call else "Debit Put"
                        
                        # Calculate PL / Exposure if possible (Need live data or cache)
                        # We use data from last update if available, or just static info
                        
                        # Exposure %
                        # We need 'val' which is in the TABLE, not necessarily in managed_spreads dict 
                        # unless we update it. Phase 10 update_positions does NOT update managed_spreads with Val.
                        # It only updates table.
                        # BUT managed_spreads has 'avg_price'.
                        
                        strikes = f"{k_long}/{k_short}"
                        stop_lvl = k_long * 0.99 if is_call else k_long * 1.01
                        
                        pos_str = f"**{strat_type}** {strikes}\nSTOP: {stop_lvl:.2f} | **ARMED**"
                        positions.append(pos_str)
                    except: continue

            if not positions:
                if reason == "LAUNCH":
                    msg = f"**Nexus Debit Online**\nNo Active Positions."
                else: 
                    return # Don't spam empty updates on schedule? User said "announce the position status", implying ONLY if exists? 
                    # "It will show Position: Debit Call..."
                    # If empty, maybe say "Flat"?
                    msg = f"**Nexus Debit Status ({reason})**\nNo Active Positions."
            else:
                pos_block = "\n".join(positions)
                msg = f"**Nexus Debit Status ({reason})**\n{pos_block}"
            
            payload = {"content": msg}
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                 async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                     if resp.status not in [200, 204]:
                         self.log_msg(f"Discord Fail: {resp.status}")
                     else:
                         self.log_msg(f"Status Announce Sent ({reason})")

        except Exception as e:
            self.log_msg(f"Announce Error: {e}")

    async def on_mount(self):
        # Setup Tables
        chain_table = self.query_one("#chain_table", DataTable)
        chain_table.cursor_type = "row"
        chain_table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "MAX PROFIT", "RETURN %", "L. DELTA")
        
        pos_table = self.query_one("#positions_table", DataTable)
        # Added STOP, PROFIT columns
        pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")
        
        self.log_msg("Nexus Debit Engine Initiated.")
        self.run_worker(self.market_data_loop)
        self.run_worker(self.account_data_loop)
        self.run_worker(self.status_scheduler_loop)
        self.run_worker(self.announce_status('LAUNCH'))
        # self.run_worker(self.fetch_managed_spreads_loop) # DISABLED (ZMQ CONTENTION)
        self.run_worker(self.auto_manager_loop)
    
    async def market_data_loop(self):
        """Streams SPY price for the 'Defense' stop trigger."""
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

    async def auto_manager_loop(self):
        """
        THE HYBRID MANAGER (Phase 10 Logic)
        1. OFFENSE: 50% Profit (1.5x on Debit)
        2. DEFENSE: 1% Strike Stop
        """
        while True:
            await asyncio.sleep(1)
            if not self.auto_exit_enabled or not self.managed_spreads:
                continue

            # Copy to avoid size change during iteration check, though usually safe if not deleting
            # But update_positions replaces the whole dict, so we might encounter concurrency issues?
            # It's running on main thread (async), so no thread concurrency, but await calls yield.
            # Safe to iterate.
            
            for key, spread in list(self.managed_spreads.items()):
                long_strike = spread.get("long_strike", 0)
                
                # SAFETY GUARD: Zero Strike
                if long_strike <= 0: continue
                
                entry_debit = abs(spread.get("avg_price", 0))
                is_call = spread.get("is_call", True) # Default True if missing, but we sync it.
                
                # Logic: 1% Rule
                if is_call: stop_level = long_strike * 0.99
                else: stop_level = long_strike * 1.01
                
                # Trigger
                if self.current_spy_price > 0:
                    triggered = False
                    if is_call and self.current_spy_price <= stop_level: triggered = True
                    if not is_call and self.current_spy_price >= stop_level: triggered = True
                    
                    if triggered:
                        self.log_msg(f"ðŸ›‘ STOP TRIGGERED: SPY {self.current_spy_price:.2f} hit limit {stop_level:.2f}")
                        await self.panic_close_spread(spread, reason="STOP_LOSS")

    @on(Button.Pressed, "#fetch_btn")
    async def on_fetch(self):
        self.run_worker(self.fetch_chain)

    async def fetch_chain(self):
        btn = self.query_one("#fetch_btn")
        btn.disabled = True
        btn.label = "SCANNING..."
        
        type_ = self.query_one("#type_select").value
        width_val = self.query_one("#width_input").value
        width = float(width_val) if width_val else 10.0
        
        strike_val = self.query_one("#strike_input").value
        target_strike = float(strike_val) if strike_val and strike_val.strip() else 0.0
        if target_strike <= 0:
            self.log_msg("⚠️ ERROR: Manual Strike Required for Debit Scan.")
            btn.disabled = False
            btn.label = "SCAN SETUP"
            return
            
        self.log_msg(f"Fetching Debit Setup: Strike {target_strike} Width {width}...")
        
        payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "strike": target_strike, "width": width}
        
        try:
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                # IV/IVR Logic
                iv = reply.get("iv", 0)
                ivr = reply.get("ivr", 0)
                price = reply.get("price", 0.0)
                
                # Update Internal Price
                if price > 0:
                    self.current_spy_price = price
                    try:
                        self.query_one("#spy_price_display", Static).update(f"SPY: {price:.2f}")
                    except: pass
                
                # Update Header - YELLOW for Visibility
                color = "white"
                if ivr < 30: color = "bold yellow"
                elif ivr > 50: color = "bold red"
                
                iv_txt = f"[{color}]IV: {iv:.1f}% | IVR: {ivr:.0f}[/]"
                try: self.query_one("#lbl_iv_status", Label).update(iv_txt)
                except: pass
                
                if ivr > 50:
                    self.log_msg(f"⚠️ HIGH VOLATILITY (IVR {ivr}). DEBIT SPREADS EXPENSIVE.")
                
                self.populate_debit_chain(reply.get("data", []), width, target_strike, ivr)
            else:
                self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")
            
        btn.disabled = False
        btn.label = "SCAN SETUP"

    @on(Button.Pressed, "#refresh_btn")
    async def on_refresh(self):
        self.run_worker(self.fetch_chain)
        
    @on(Button.Pressed, "#execute_btn")
    async def on_exec(self):
        self.run_worker(self.execute_trade)

    @on(Button.Pressed, "#cancel_btn")
    async def on_cancel(self):
        # This button logic is placeholder. In reality it should act on selected row in 'positions_table'.
        self.log_msg("Select a position to close (Not Implemented in UI Selection yet)")
        # For now, if we have a 'selected_spread' that matches a managed one, maybe close it?
        # Leaving as is per user provided code, just fixing the logic.

    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            
            # Prob Adj Logic
            if ivr < 30: 
                prob_txt = "[bold green]Cheap (Low IV)[/]"
            elif ivr > 50:
                prob_txt = "[bold red]Expensive[/]"
            else:
                prob_txt = "Neutral"

            for s in chain_data:
                 ask_short = float(s.get("ask_short", 0))
                 bid_long = float(s.get("bid_long", 0))
                 
                 debit = ask_short - bid_long
                 if debit <= 0: debit = 0.01 
                 
                 width_val = abs(float(s["short"]) - float(s["long"]))
                 max_profit_theo = width_val - debit
                 max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
                 
                 l_strike = float(s["short"]) 
                 s_strike = float(s["long"])
                 
                 is_call = l_strike < s_strike
                 if is_call: 
                     be = l_strike + debit
                 else: 
                     be = l_strike - debit
                 
                 # Calc Dist % (Only if price valid)
                 if cur_price > 1.0:
                     if is_call:
                         dist_pct = ((be - cur_price) / cur_price) * 100
                     else:
                         dist_pct = ((cur_price - be) / cur_price) * 100
                         
                     if dist_pct <= 0: dist_style = "[bold green]"
                     elif dist_pct < 0.5: dist_style = "[bold yellow]"
                     else: dist_style = "[white]"
                     
                     dist_str = f"{dist_style}{dist_pct:.2f}%[/]"
                 else:
                     dist_str = "---"

                 roc_style = "bold green" if max_roc > 80 else "bold yellow"
                 
                 row = [
                     s["expiry"], str(s["dte"]),
                     f"{l_strike:.0f} (L)", f"{s_strike:.0f} (S)",
                     f"${debit:.2f}", 
                     dist_str,
                     prob_txt,
                     Text(f"{max_roc:.1f}%", style=roc_style),
                     f"{be:.2f}"
                 ]
                 
                 key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                 table.add_row(*row, key=key)
                 
        except Exception as e:
            self.log_msg(f"Populate Error: {e}")
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        # Filter for Chain Table only
        if event.data_table.id != "chain_table":
            return
            
        if not event.row_key.value: return
        
        try:
            parts = event.row_key.value.split("|")
            if len(parts) < 6: return
            
            # parts: [short_sym, long_sym, debit, l_strike, s_strike, width]
            debit = float(parts[2])
            l_strike = float(parts[3]) 
            s_strike = float(parts[4])
            width = float(parts[5])

            # STORE UNIT VALUES
            self.selected_unit_debit = debit
            self.selected_unit_width = width
            self.selected_strikes = f"{l_strike:.0f}/{s_strike:.0f}"
            
            # Set Setup Label safely
            try:
                self.query_one("#lbl_spread", Static).update(self.selected_strikes)
            except: pass

            # Update ROC (Rate of Return is constant %)
            max_profit_theo = width - debit
            max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
            roc_style = "[bold green]" if max_roc > 80 else "[bold yellow]"
            try:
                self.query_one("#lbl_roc", Static).update(f"{roc_style}{max_roc:.1f}%[/]")
            except: pass
            
            # Update Stop Trigger (Price Level is constant)
            try:
                is_call = l_strike < s_strike
                stop_price = l_strike * 0.99 if is_call else l_strike * 1.01
                self.query_one("#lbl_stop_trigger", Static).update(f"${stop_price:.2f}")
            except: pass

            # Enable Buttons
            try:
                self.query_one("#execute_btn", Button).disabled = False
            except: pass
            
            # RECALC TOTALS (Scales Cost/Profit)
            self.recalc_totals()

        except Exception as e:
            self.log_msg(f"Selection Error: {e}")
        except Exception as e:
            self.log_msg(f"Selection Error: {e}")

    @on(DataTable.RowSelected, "#positions_table")
    def on_pos_selected(self, event: DataTable.RowSelected):
        """Captures selection for potential closing."""
        if event.data_table.id != "positions_table": return
        
        row_key = event.row_key
        row = self.query_one("#positions_table").get_row(row_key)
        
        # Row: STRATEGY, STRIKES, DTE, QTY...
        strategy = str(row[0])
        strikes = str(row[1])
        qty = str(row[3])
        
        self.log_msg(f"Action: Selected {strategy} {strikes}")
        
        # Enable Close Button
        self.query_one("#cancel_btn").disabled = False
        
        # Store for logic
        self.selected_position_row = {
            "strategy": strategy,
            "strikes": strikes,
            "qty": qty
        }
    def recalc_totals(self):
        """Updates Debit Cost and Target Profit based on Lot Size."""
        try:
            qty_val = self.query_one("#qty_input").value
            qty = int(qty_val) if qty_val and qty_val.strip() else 1
        except: 
            qty = 1
            
        unit_debit = getattr(self, "selected_unit_debit", 0.0)
        
        if unit_debit > 0:
            # Scale: Unit * Qty * 100 (Contract Multiplier)
            total_cost = unit_debit * qty * 100
            
            # Target is 50% of Debit
            total_target = (total_cost * 0.50)
            
            # Update Labels
            self.query_one("#lbl_debit", Static).update(f"${total_cost:,.2f}")
            self.query_one("#lbl_profit", Static).update(f"${total_target:,.2f}")

    @on(Input.Changed, "#qty_input")
    def on_qty_change(self, event):
        self.recalc_totals()
    async def execute_trade(self):
        if not self.selected_spread: return
        qty_val = self.query_one("#qty_input").value
        qty = int(qty_val) if qty_val else 1
        
        self.log_msg(f"Buying {qty}x Spreads...")
        
        # Send to Backend
        # CRITICAL ADAPTATION: Use side="SELL" logic from ts_nexus.py
        # ts_nexus "SELL" => Sell Short Leg (Open), Buy Long Leg (Open)
        # For Debit Spread: We DO WANT to Sell Short Leg and Buy Long Leg.
        # So we use side="SELL".
        
        payload = {
            "cmd": "EXECUTE_SPREAD",
            "side": "SELL", # [FIX] Aligns with ts_nexus 'Vertical Spread' logic
            "long_sym": self.selected_spread["long_sym"],
            "short_sym": self.selected_spread["short_sym"],
            "qty": qty,
            "price": self.selected_spread["debit"]
        }
        await self.req_sock.send_json(payload)
        reply = await self.req_sock.recv_json()
        self.log_msg(f"Order: {reply.get('msg')}")

    @on(Button.Pressed, "#cancel_btn")
    async def on_cancel(self):
        await self.panic_close()

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
        
        # Match back to managed_spreads
        # Debit Sniper mainly handles Debit Calls/Puts?
        # DEBIT CALL = Long Call (Buy Open). Close = Sell.
        # DEBIT PUT = Long Put (Buy Open). Close = Sell.
        # Credit? If we see Credit, we Buy to Close.
        
        target_spread = None
        target_k = p['strikes'].split('/') 
        try:
             k1 = float(target_k[0])
             k2 = float(target_k[1])
        except: return 
        
        for sym, data in self.managed_spreads.items():
            # Check Strikes (Allow small float tolerance)
            # data has long_strike and short_strike
            if abs(data.get('long_strike', 0) - k1) < 0.1 and abs(data.get('short_strike', 0) - k2) < 0.1:
                target_spread = data
                break
        
        if not target_spread:
            self.log_msg("Error: Could not find spread symbols for selection.")
            return

        # Determine logic
        # If "CREDIT": We are Short. Close = Buy.
        # If "DEBIT": We are Long. Close = Sell.
        
        is_credit = "CREDIT" in p['strategy']
        close_side = "BUY" if is_credit else "SELL" # Close Long = Sell.
        
        payload = {
            "cmd": "EXECUTE_SPREAD", 
            "short_sym": target_spread['short_sym'],
            "long_sym": target_spread['long_sym'],
            "qty": int(p['qty']),
            "price": 0.0, # Market
            "stop_trigger": 0.0,
            "order_type": "MARKET",
            "side": close_side 
        }
        
        try:
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                self.log_msg(f"Close Order Sent! ID: {reply.get('order_id')}")
            else:
                self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")

    def log_msg(self, msg):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        self.query_one("#activity_log", Log).write(f"[{t}] {msg}")

if __name__ == "__main__":
    DebitSniperApp().run()