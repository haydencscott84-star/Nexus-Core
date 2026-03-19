
# PATCH PHASE 9: UI & BOT LOGIC (FINAL)
# Targets: nexus_debit_downloaded.py, nexus_spreads_downloaded.py

DEBIT_FILE = "nexus_debit_downloaded.py"
SPREADS_FILE = "nexus_spreads_downloaded.py"

# --- NEXUS DEBIT ---

DEBIT_COMPOSE = r'''
    def compose(self) -> ComposeResult:
        with Horizontal(id="control_bar"):
            yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")
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
                
                yield Label("MAX PROFIT:", classes="exec-label")
                yield Static("-", id="lbl_profit", classes="exec-value")
                
                yield Label("RETURN (ROC):", classes="exec-label")
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
'''

DEBIT_ON_MOUNT = r'''
    async def on_mount(self):
        # Setup Tables
        chain_table = self.query_one("#chain_table", DataTable)
        chain_table.cursor_type = "row"
        chain_table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "MAX PROFIT", "RETURN %", "L. DELTA")
        
        pos_table = self.query_one("#positions_table", DataTable)
        # Added STOP, PROFIT columns
        pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "VALUE", "STOP (1%)", "PT (150%)")
        
        self.log_msg("Nexus Debit Engine Initiated.")
        self.run_worker(self.market_data_loop)
        self.run_worker(self.account_data_loop)
        self.run_worker(self.fetch_managed_spreads_loop)
        self.run_worker(self.auto_manager_loop)
'''

DEBIT_MANAGER = r'''
    async def auto_manager_loop(self):
        """
        THE HYBRID MANAGER (Phase 9 Logic)
        1. OFFENSE: 50% Profit (1.5x on Debit)
        2. DEFENSE: 1% Strike Stop
        """
        while True:
            await asyncio.sleep(1)
            if not self.auto_exit_enabled or not self.managed_spreads:
                continue

            for short_sym, spread in self.managed_spreads.items():
                if "long_sym" not in spread: continue
                
                long_strike = spread.get("long_strike", 0)
                entry_debit = abs(spread.get("avg_price", 0))
                is_call = "C" in spread.get("long_sym", "")
                
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
'''

DEBIT_UPDATE_POS = r'''
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        import datetime
        
        # 1. GROUP
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
            
        processed_syms = set()
        
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
                    if k_short > k_long: # Bull Call
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

                    # LOGIC: 1% Stop, 1.5x Profit
                    stop_lvl = k_long * 0.99
                    profit_target = cost * 1.50
                    
                    strikes_str = f"{k_long}/{k_short}"
                    table.add_row("DEBIT CALL", strikes_str, dte_str, str(qty), pl_str, f"${val:.2f}", f"{stop_lvl:.2f}", f"${profit_target:.0f}")
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))

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
                    profit_target = cost * 1.50
                    
                    strikes_str = f"{k_long}/{k_short}"
                    table.add_row("DEBIT PUT", strikes_str, dte_str, str(qty), pl_str, f"${val:.2f}", f"{stop_lvl:.2f}", f"${profit_target:.0f}")
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))
'''

# --- NEXUS SPREADS ---

SPREADS_COMPOSE = r'''
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
'''

SPREADS_ON_MOUNT = r'''
    async def on_mount(self):
        # Setup Tables
        chain_table = self.query_one("#chain_table", DataTable)
        chain_table.cursor_type = "row"
        chain_table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "YIELD", "RISK", "R/R", "BE")
        
        pos_table = self.query_one("#positions_table", DataTable)
        # Added STOP, PROFIT columns
        pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "MKT VAL", "STOP (0.5pt)", "PT (50%)")
        
        self.log_msg("System Ready. Waiting for data...")
        self.fetch_last_known_price()
        self.run_worker(self.market_data_loop)
        self.run_worker(self.account_data_loop)
        self.run_worker(self.fetch_managed_spreads_loop)
        self.run_worker(self.active_quote_loop)
        self.run_worker(self.auto_manager_loop) # START THE BOT
'''

# New Manager Loop for Spreads (0.5 pt Stop)
# Replaces active_quote_loop with itself + new manager loop
SPREADS_MANAGER_INJECT = r'''
    async def auto_manager_loop(self):
        """
        Active Manager for Credit Spreads (Phase 9)
        1. DEFENSE: 0.5 Point Constraint (Stop if price breaches Short Strike +/- 0.5)
        """
        while True:
            await asyncio.sleep(1)
            if not self.managed_spreads: continue
            
            for short_sym, spread in self.managed_spreads.items():
                short_strike = spread.get("short_strike", 0)
                is_call = "C" in short_sym
                
                # Logic: 0.5 Point Constraint
                if is_call: 
                    # Bear Call: Stop if Price rises to (Short - 0.5)
                    # e.g. Sold 705. Stop at 704.5.
                    stop_level = short_strike - 0.5
                else:
                    # Bull Put: Stop if Price falls to (Short + 0.5)
                    # e.g. Sold 600. Stop at 600.5.
                    stop_level = short_strike + 0.5
                    
                # Trigger Check
                # Need current SPY price. Nexus Spreads stores it in self.current_spy_price?
                # Check __init__: self.current_spy_price = 0.0
                # Check market_data_loop updates it? Yes.
                
                if self.current_spy_price > 0:
                    triggered = False
                    if is_call and self.current_spy_price >= stop_level: triggered = True
                    if not is_call and self.current_spy_price <= stop_level: triggered = True
                    
                    if triggered:
                        self.log_msg(f"ðŸ›‘ STOP TRIGGERED: SPY {self.current_spy_price:.2f} breached {stop_level:.2f}")
                        # Panic Close
                        self.selected_spread = spread # Set for close
                        await self.panic_close()
                        await asyncio.sleep(5) # Prevent spam

    async def active_quote_loop(self):
'''

SPREADS_UPDATE_POS_FINAL = r'''
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        import datetime
        
        pos_map = {p.get("Symbol"): p for p in positions}
        processed_syms = set()
        
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
                    initial_val = -credit_captured
                    target_val = initial_val * 0.50 
                    
                    if is_call: stop_lvl = s["strike"] - 0.5
                    else: stop_lvl = s["strike"] + 0.5
                    
                    table.add_row(type_str, strikes_str, dte_str, str(qty), pl_str, f"${val_net:.2f}", f"{stop_lvl:.2f}", f"${target_val:.0f}", key=key_id)
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
'''

def replace_block(file_path, start_me, end_me, content):
    try:
        with open(file_path, 'r') as f: data = f.read()
        if start_me in data:
            pre, post = data.split(start_me, 1)
            # Find closest end marker
            if end_me in post:
                body, remainder = post.split(end_me, 1)
                final = pre + content.strip() + "\n    \n    " + end_me + remainder
                with open(file_path, 'w') as f: f.write(final)
                print(f"Patched: {file_path}")
            else: print(f"End marker '{end_me}' not found in {file_path}")
        else: print(f"Start marker '{start_me}' not found in {file_path}")
    except Exception as e: print(f"Error: {e}")

if __name__ == "__main__":
    # DEBIT
    replace_block(DEBIT_FILE, "def compose(self) -> ComposeResult:", "def update_positions(self, positions):", DEBIT_COMPOSE)
    replace_block(DEBIT_FILE, "async def on_mount(self):", "async def market_data_loop(self):", DEBIT_ON_MOUNT)
    replace_block(DEBIT_FILE, "async def auto_manager_loop(self):", "async def fetch_chain(self):", DEBIT_MANAGER)
    replace_block(DEBIT_FILE, "def update_positions(self, positions):", "async def account_data_loop(self):", DEBIT_UPDATE_POS)

    # SPREADS
    replace_block(SPREADS_FILE, "def compose(self) -> ComposeResult:", "async def on_mount(self):", SPREADS_COMPOSE)
    replace_block(SPREADS_FILE, "async def on_mount(self):", "async def active_quote_loop(self):", SPREADS_ON_MOUNT)

    # Inject new loop before active_quote_loop:
    # Instead of replacing active_quote_loop completely, we replace "async def active_quote_loop(self):" with the new method + the start of active_quote_loop
    # Wait, replace_block logic appends the end_me. 
    # If I replace `async def active_quote_loop` with `NewLoop... async def active_quote_loop`, 
    # my function `replace_block` will see `end_marker` is "async def active_quote_loop"
    # So it splits there. The `body` is what's BEFORE `active_quote_loop`.
    # Wait, `active_quote_loop` is the Method Name Line.
    # In `on_mount`, I changed `on_mount` content.
    # But `auto_manager_loop` definition is missing in Spreads.
    # I need to insert it.
    # The previous `replace_block` replaced content BETWEEN start and end.
    # To INSERT, I can target the method BEFORE `active_quote_loop`? 
    # `force_refresh_loop` is before it.
    # Let's replace `force_refresh_loop` body? No.
    # Let's do a targeted replace string.
    
    with open(SPREADS_FILE, 'r') as f: s_data = f.read()
    # Inject before active_quote_loop
    if "async def active_quote_loop(self):" in s_data and "async def auto_manager_loop(self):" not in s_data:
        s_data = s_data.replace("async def active_quote_loop(self):", SPREADS_MANAGER_INJECT.strip() + "\n\n    async def active_quote_loop(self):")
        with open(SPREADS_FILE, 'w') as f: f.write(s_data)
        print("Injected Spreads Manager Loop")
    
    replace_block(SPREADS_FILE, "def update_positions(self, positions):", "async def fetch_managed_spreads_loop(self):", SPREADS_UPDATE_POS_FINAL)
