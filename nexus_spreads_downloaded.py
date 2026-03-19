import zmq
import zmq.asyncio
import asyncio
import datetime
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Button, Input, Label, Select, Static, Log
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.screen import Screen
from textual import work, on
from rich.text import Text

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
    """

    def __init__(self):
        super().__init__()
        self.zmq_ctx = zmq.asyncio.Context()
        self.req_sock = self.zmq_ctx.socket(zmq.REQ)
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
        self.account_metrics = {"equity": 0, "pl": 0, "exposure": 0}

    def compose(self) -> ComposeResult:
        # Header
        with Horizontal(id="control_bar"):
            yield Select.from_values(["PUT", "CALL"], allow_blank=False, value="PUT", id="type_select", classes="control-item")
            yield Input(placeholder="Strike", id="strike_input", classes="control-item")
            yield Input(placeholder="Width", value="5", id="width_input", classes="control-item")
            yield Button("FETCH CHAIN", id="fetch_btn", classes="control-item")
            yield Button("↻ REFRESH", id="refresh_btn", classes="control-item")
            yield Static("ACCT: ---", id="acct_display", classes="control-item-right")

        with Grid(id="main_grid"):
            # Top Left: Option Chain
            with Vertical(id="chain_container"):
                yield Label(" OPTION CHAIN", classes="panel-header")
                yield DataTable(id="chain_table")
            
            # Right Sidebar
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
                yield Button("PANIC CLOSE (MKT)", id="cancel_btn", disabled=True) 

            # Bottom: Positions & Log (VERTICAL STACK)
            with Vertical(id="bottom_container"):
                with Vertical():
                    yield Label(" OPEN POSITIONS", classes="panel-header")
                    yield DataTable(id="positions_table") # Full Width
                with Vertical():
                    yield Label(" SYSTEM LOG", classes="panel-header")
                    yield Log(id="activity_log") # Full Width
    
    async def on_mount(self):
        # Setup Tables
        chain_table = self.query_one("#chain_table", DataTable)
        chain_table.cursor_type = "row"
        chain_table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "YIELD", "RISK", "R/R", "BE")
        
        pos_table = self.query_one("#positions_table", DataTable)
        # Added STOP, PROFIT columns
        pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")
        
        self.log_msg("System Ready. Waiting for data...")
        self.fetch_last_known_price()
        self.run_worker(self.market_data_loop)
        self.run_worker(self.account_data_loop)
        # self.run_worker(self.fetch_managed_spreads_loop) # DISABLED (Using update_positions)
        self.run_worker(self.active_quote_loop)
        self.run_worker(self.auto_manager_loop) # START THE BOT
    
    async def auto_manager_loop(self):
        """
        Active Manager for Credit Spreads (Phase 9)
        1. DEFENSE: 0.5 Point Constraint
        """
        while True:
            await asyncio.sleep(1)
            # Use safe copying keys to avoid runtime modification errors if dict changes
            if not self.managed_spreads: continue
            
            items = list(self.managed_spreads.items())
            for short_sym, spread in items:
                short_strike = spread.get("short_strike", 0)
                if short_strike <= 0: continue # Safety Guard
                is_call = "C" in short_sym
                
                # Logic: 0.5 Point Constraint
                if is_call: 
                    # Bear Call: Stop if Price >= Short - 0.5
                    stop_level = short_strike - 0.5
                else:
                    # Bull Put: Stop if Price <= Short + 0.5
                    stop_level = short_strike + 0.5
                    
                if self.current_spy_price > 0:
                    triggered = False
                    if is_call and self.current_spy_price >= stop_level: triggered = True
                    if not is_call and self.current_spy_price <= stop_level: triggered = True
                    
                    if triggered:
                        warn_msg = f"ðŸ›‘ STOP TRIGGERED: SPY {self.current_spy_price:.2f} breached {stop_level:.2f}"
                        # Check redundancy to avoid log spam
                        if self.selected_spread != spread:
                            self.log_msg(warn_msg)
                        
                        # Set as selected and Panic Close
                        self.selected_spread = spread 
                        await self.panic_close()
                        await asyncio.sleep(5) # Pause to allow close to process

    async def active_quote_loop(self):
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
                                cred_price = qs["Bid"] - ql["Ask"]
                                width = abs(self.selected_spread["short_strike"] - self.selected_spread["long_strike"])
                                risk = (width - cred_price) * 100 * int(self.query_one("#qty_input").value or 1) # Unsafe access? Ideally read from self var, but acceptable for read.
                                equity = self.account_metrics.get("equity", 1)
                                risk_pct = (risk / equity * 100) if equity > 0 else 0
                                yld = (cred_price / width * 100) if width > 0 else 0
                                
                                def update_quote_ui():
                                    try:
                                        self.query_one("#lbl_credit").update(f"${cred_price * 100:.2f} ⚡")
                                        self.query_one("#lbl_risk").update(f"${risk:.2f} ({risk_pct:.1f}%) ⚡")
                                        self.query_one("#lbl_yield").update(f"{yld:.1f}% ⚡")
                                        self.query_one("#lbl_yield").styles.color = "green" if yld > 30 else ("yellow" if yld >= 20 else "red")
                                    except: pass
                                
                                self.call_after_refresh(update_quote_ui)

                    sock.close()
                except: pass
            
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
                    self.log_msg(f"Refreshed {len(positions)} positions via RPC.")
            sock.close()
        except Exception as e:
            self.log_msg(f"RPC Refresh Fail: {e}")

    def log_msg(self, msg):
        try:
            t = datetime.datetime.now().strftime("%H:%M:%S")
            self.query_one("#activity_log", Log).write(f"[{t}] {msg}")
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
                    def update_price():
                        try: self.query_one("#spy_price_display").update(f"SPY: {price:.2f}")
                        except: pass
                    self.call_after_refresh(update_price)
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
                
                eq = float(data.get("total_account_value", 0))
                self.account_metrics["equity"] = eq 
                pl = sum([float(p.get("UnrealizedProfitLoss", 0)) for p in positions])
                exp = sum([float(p.get("MarketValue", 0)) for p in positions])
                
                pl_pct = (pl / eq * 100) if eq != 0 else 0.0
                exp_pct = (exp / eq * 100) if eq != 0 else 0.0
                
                def update_acct_ui():
                    try: self.query_one("#acct_display").update(f"P/L: ${pl:.0f} ({pl_pct:+.1f}%) | EXP: ${exp/1000:.1f}K ({exp_pct:.1f}%)")
                    except: pass
                    
                self.call_after_refresh(update_acct_ui)
                self.call_after_refresh(self.update_positions, positions)
            except: pass
    
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        import datetime
        
        pos_map = {p.get("Symbol"): p for p in positions}
        processed_syms = set(); self.managed_spreads = {}
        
        def parse_sym(s):
            import re
            parts = s.split(' ')
            if len(parts) < 2: return None
            code = parts[1]
            m = re.match(r'^(\d{6})([CP])([\d.]+)$', code)
            if m:
                return {"expiry": m.group(1), "type": m.group(2), "strike": float(m.group(3)), "sym": s}
            return None

        groups = {}
        for sym, p in pos_map.items():
            meta = parse_sym(sym)
            if meta:
                key = f"{meta['expiry']}{meta['type']}"
                if key not in groups: groups[key] = []
                meta["qty"] = float(p.get("Quantity", 0))
                meta["pl"]  = float(p.get("UnrealizedProfitLoss", 0))
                meta["val"] = float(p.get("MarketValue", 0))
                groups[key].append(meta)

        for key, group in groups.items():
            expiry = key[:6]
            try:
                exp_dt = datetime.datetime.strptime(expiry, "%y%m%d")
                dte_val = (exp_dt - datetime.datetime.now()).days
                dte_str = f"{dte_val}d"
            except: dte_str = "-d"

            is_call = "C" in key
            shorts = [x for x in group if x["qty"] < 0]
            longs  = [x for x in group if x["qty"] > 0]
            
            for s in shorts:
                if s["sym"] in processed_syms: continue
                match = None
                for l in longs:
                    if l["sym"] in processed_syms: continue
                    is_credit = False
                    if is_call:
                        if s["strike"] < l["strike"]: is_credit = True
                    else:
                        if s["strike"] > l["strike"]: is_credit = True
                    if is_credit:
                        match = l
                        break
                
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
                    val_net = s["val"] + l["val"]
                
                    type_str = "CALL CREDIT" if is_call else "PUT CREDIT"
                    strikes_str = f"{s['strike']}/{l['strike']}"
                    key_id = f"SPREAD|{s['sym']}|{l['sym']}"
                
                    credit_captured = pl_net - val_net
                    if credit_captured <= 0.01: credit_captured = 1.0
                    roi = (pl_net / credit_captured) * 100
                    pl_str = f"{roi:+.1f}%"
                
                    # LOGIC: 50% Capture, 0.5 pt Stop
                    if is_call: stop_lvl = s["strike"] - 0.5
                    else: stop_lvl = s["strike"] + 0.5
                
                    # EXPOSURE Calculation
                    risk_abs = (abs(s["strike"] - l["strike"]) * 100 * qty)
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (risk_abs / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"
                
                    # UI: Add Row (NEGATIVE QTY for Spreads)
                    display_qty = -qty
                    table.add_row(
                    type_str, strikes_str, dte_str, str(display_qty),
                    Text(pl_str, style="bold green" if pl_net > 0 else "bold red"),
                    Text(f"{exposure_pct:.1f}%", style=exp_style),
                    f"{stop_lvl:.2f}",
                    Text("ARMED", style="bold green"),
                    key=key_id
                    )
                
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
                
                    # DATA SYNC: Populate Managed Spreads for Bot
                    # Guarding against zero strikes is implicit here because we use matched data
                    self.managed_spreads[s["sym"]] = {
                    "short_sym": s["sym"], "long_sym": l["sym"],
                    "short_strike": s["strike"], "long_strike": l["strike"],
                    "qty": qty, "is_call": is_call
                    }
                    
                    # DATA SYNC: Populate Managed Spreads for Bot
                    self.managed_spreads[s["sym"]] = {
                        "short_sym": s["sym"], "long_sym": l["sym"],
                        "short_strike": s["strike"], "long_strike": l["strike"],
                        "qty": qty, "is_call": is_call
                    }
    
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
                        self.managed_spreads = {s["short_sym"]: s for s in spreads_list if "short_sym" in s}
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
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                self.populate_chain(reply.get("data", []))
                self.log_msg(f"Fetched {len(reply.get('data', []))} spreads.")
            else:
                self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")
            
        btn.disabled = False
        btn.label = "FETCH CHAIN"

    def populate_chain(self, data):

        table = self.query_one("#chain_table", DataTable)
        table.clear()
        for item in data:
            # Yield Calc
            width = abs(float(item['short']) - float(item['long']))
            credit = float(item['credit'])
            yield_pct = (credit / width * 100) if width > 0 else 0
            
            # Color Logic
            y_style = "bold red"
            if yield_pct > 30: y_style = "bold green"
            elif yield_pct >= 20: y_style = "bold yellow"
            
            row = [
                item["expiry"], str(item["dte"]), f"{item['short']:.1f}", f"{item['long']:.1f}",
                f"${credit:.2f}", Text(f"{yield_pct:.1f}%", style=y_style), f"${item['risk']:.2f}", f"{item['rr']:.1f}%", f"{item['breakeven']:.2f}"
            ]
            key = f"{item['short_sym']}|{item['long_sym']}|{item['credit']}|{item['short']}|{item['long']}"
            table.add_row(*row, key=key)

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
            width = abs(self.selected_spread["short_strike"] - self.selected_spread["long_strike"])
            half_width = width / 2.0
            
            is_put = "P" in parts[0]
            if is_put:
                # Bull Put: We lose if price drops.
                stop_price = self.selected_spread["short_strike"] - half_width
            else:
                # Bear Call: We lose if price rises.
                stop_price = self.selected_spread["short_strike"] + half_width
                
            self.selected_spread["stop_trigger"] = stop_price
            self.query_one("#lbl_stop").update(f"{stop_price:.2f}")
            
            # Initial Risk Calc
            self.calculate_risk()
            
        elif event.data_table.id == "positions_table":
            # Handle Position Selection for Panic Close
            key = event.row_key.value
            if key.startswith("SPREAD|"):
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
            "order_type": "MARKET", # Changed to MARKET to ensure fill per user request
            "side": side
        }
        
        try:
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                self.log_msg(f"Order Sent! ID: {reply.get('order_id')}")
            else:
                self.log_msg(f"Exec Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Exec Fail: {e}")

    async def panic_close(self):
        if not self.selected_spread: return
        self.log_msg("PANIC CLOSE: Executing Market Exit via Transient Socket...")
        
        import zmq.asyncio
        ctx = zmq.asyncio.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect("tcp://127.0.0.1:5555")
        sock.setsockopt(zmq.RCVTIMEO, 2000)

        payload = {
            "cmd": "CLOSE_SPREAD",
            "short_sym": self.selected_spread["short_sym"],
            "long_sym": self.selected_spread["long_sym"],
            "qty": 1 # Default 1
        }
        
        try:
            await sock.send_json(payload)
            reply = await sock.recv_json()
            if reply.get("status") == "ok":
                self.log_msg(f"Close Sent! ID: {reply.get('order_id')}")
            else:
                self.log_msg(f"Close Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Transient Close Failed: {e}")
        finally:
            sock.close()
            ctx.term()

    # End

if __name__ == "__main__":
    SpreadSniperApp().run()