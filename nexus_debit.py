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
DEFAULT_ROI_TARGET = 0.50 # +50% Profit Target (Fixed)
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
    
    .control-item { margin-right: 1; }
    .control-item-right { margin-left: 2; color: #58a6ff; text-style: bold; content-align: right middle; width: 1fr; }
    #type_select { width: 10; }
    #strike_input { width: 10; }
    #width_input { width: 10; }
    #slip_input { width: 10; }
    #stop_trigger_input { width: 100%; background: #0d1117; border: solid #30363d; }
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
        # ZMQ SETUP MOVED TO on_mount TO PREVENT ASYNCIO CONTEXT CONFLICT
        self.zmq_ctx = None
        self.req_sock = None
        self.sub_sock = None
        self.acct_sock = None

        # STATE
        self.current_spy_price = 0.0
        self.selected_spread = None
        self.managed_spreads = {} 
        self.account_metrics = {"equity": 0, "pl": 0}
        self.manual_stops = {} # [NEW] Persistence for Manual Stops
        
        # HYBRID MANAGER CONFIG
        self.auto_exit_enabled = True
        self._last_positions_json = None # Cache for deduplication

    async def on_mount(self):
        # [FIX] ZMQ Context must be created inside the Async Event Loop
        self.log_msg("Init: Starting ZMQ Context...")
        self.zmq_ctx = zmq.asyncio.Context()
        
        # EXEC SOCKET
        self.req_sock = self.zmq_ctx.socket(zmq.REQ)
        self.req_sock.setsockopt(zmq.LINGER, 0)
        self.req_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
        self.log_msg(f"Init: Connected to Exec at {ZMQ_PORT_EXEC}")
        
        # SPY STREAM
        self.sub_sock = self.zmq_ctx.socket(zmq.SUB)
        self.sub_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_MARKET}")
        self.sub_sock.subscribe(b"SPY")
        
        # ACCT STREAM
        self.acct_sock = self.zmq_ctx.socket(zmq.SUB)
        self.acct_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_ACCOUNT}")
        self.acct_sock.subscribe(b"") # [FIX] Subscribe to ALL topics to ensure receipt
        
        # Setup Tables
        chain_table = self.query_one("#chain_table", DataTable)
        chain_table.cursor_type = "row"
        chain_table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "MAX PROFIT", "RETURN %", "L. DELTA")
        
        pos_table = self.query_one("#positions_table", DataTable)
        pos_table.cursor_type = "row"
        # Added STOP, PROFIT columns
        pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")
        
        self.log_msg("Nexus Debit Engine Initiated.")
        self.run_worker(self.load_initial_data()) # load state immediately
        self.run_worker(self.market_data_loop)
        self.run_worker(self.account_data_loop)
        self.run_worker(self.status_scheduler_loop)
        self.run_worker(self.announce_status('LAUNCH'))
        self.run_worker(self.load_stops()) # [NEW] Load Manual Stops
        self.run_worker(self.auto_manager_loop)

    def reconnect_req_socket(self):
        """Destroys and recreates the REQ socket to clear EFSM errors."""
        try:
            self.req_sock.close()
            self.req_sock = self.zmq_ctx.socket(zmq.REQ)
            self.req_sock.setsockopt(zmq.LINGER, 0) # [FIX]
            self.req_sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
            self.log_msg(f"⚠️ ZMQ REQ Socket Reset (Port {ZMQ_PORT_EXEC}).")
        except Exception as e:
            self.log_msg(f"Reset Error: {e}")

    async def robust_send(self, payload, timeout_ms=2500):
        """
        Sends a request and waits for reply with timeout.
        On timeout/error, resets the socket to prevent EFSM lockups.
        """
        try:
            # self.log_msg(f"DEBUG: Sending to {ZMQ_PORT_EXEC}...")
            await self.req_sock.send_json(payload)
            if await self.req_sock.poll(timeout_ms):
                reply = await self.req_sock.recv_json()
                return reply
            else:
                self.log_msg("⚠️ Timeout: No Reply from Backend.")
                self.reconnect_req_socket() # Critical: Reset state
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
        with Horizontal(id="control_bar"):
            yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")
            yield Label("IV: --% | IVR: --", id="lbl_iv_status", classes="control-item")
            yield Select.from_values(["CALL", "PUT"], allow_blank=False, value="CALL", id="type_select", classes="control-item")
            yield Input(placeholder="Strike", id="strike_input", classes="control-item")
            yield Input(placeholder="Width", value="30", id="width_input", classes="control-item")
            yield Input(placeholder="Slip", value="0.05", id="slip_input", classes="control-item")
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
                yield Input(placeholder="Auto", id="stop_trigger_input", classes="control-item")
                
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
        # SYNC LOGIC: Ported from Trader Dashboard V2 (Time-Based Grouping)
        import json
        try:
            # DEDUPLICATION: Avoid redraw if payload is identical
            current_json = json.dumps(positions, sort_keys=True)
            if self._last_positions_json == current_json:
                return
            self._last_positions_json = current_json
        except: pass

        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        self.managed_spreads = {}
        processed_syms = set()
        
        from collections import defaultdict
        import re

        # 1. Map Positions by Symbol
        pos_map = {p.get("Symbol"): p for p in positions}
        
        # 2. Group by Timestamp (The "Source of Truth" for Multi-Leg Orders)
        time_groups = defaultdict(list)
        for p in positions:
            # Try various timestamp fields (TradeStation API varies)
            ts = p.get("Timestamp") or p.get("DateAcquired") or p.get("Created")
            if ts:
                time_groups[ts].append(p)
            else:
                # Fallback for positions without timestamp (should be rare for filled orders)
                # We treat them as orphans for now, or could group by expiry if absolutely needed.
                pass

        # 3. Process Groups (Identify Spreads)
        for ts, group in time_groups.items():
            if len(group) == 2:
                p1 = group[0]; p2 = group[1]
                q1 = float(p1.get("Quantity", 0)); q2 = float(p2.get("Quantity", 0))
                
                # SPREAD CRITERIA: Equal Magnitude, Opposite Sign
                if abs(q1) == abs(q2) and (q1 * q2 < 0):
                    sym1 = p1.get("Symbol"); sym2 = p2.get("Symbol")
                    if sym1 in processed_syms or sym2 in processed_syms: continue
                    
                    # Determine Short/Long
                    short_p = p1 if q1 < 0 else p2
                    long_p = p2 if q1 < 0 else p1
                    
                    short_sym = short_p.get("Symbol")
                    long_sym = long_p.get("Symbol")
                    
                    # Mark processed
                    processed_syms.add(short_sym)
                    processed_syms.add(long_sym)
                    
                    # Calc Stats
                    pl_net = float(short_p.get("UnrealizedProfitLoss", 0)) + float(long_p.get("UnrealizedProfitLoss", 0))
                    val_net = float(short_p.get("MarketValue", 0)) + float(long_p.get("MarketValue", 0))
                    qty = abs(int(short_p.get("Quantity", 0)))
                    
                    cost_basis = val_net - pl_net
                    pl_str = "0.0%"
                    if cost_basis != 0:
                        pl_pct = (pl_net / abs(cost_basis) * 100)
                        pl_str = f"{pl_pct:+.1f}%"
                        
                    # DTE Parsing
                    dte_str = "-"
                    try:
                         # Expiry from Symbol or ExpirationDate field
                         if short_p.get("ExpirationDate"):
                             d = datetime.datetime.fromisoformat(short_p['ExpirationDate'].replace('Z', '+00:00'))
                             now = datetime.datetime.now(d.tzinfo)
                             days = (d.date() - now.date()).days
                             dte_str = f"{days}d"
                    except: pass
                    
                    # Strategy Labeling
                    try:
                        # Parse Strikes (e.g. "... P670")
                        def parse_k(s):
                            m = re.search(r'([CP])([\d\.]+)$', s.replace(' ', ''))
                            if not m: return None, 0.0
                            raw_k = float(m.group(2))
                            # Handle massive multipliers (e.g. 670000 -> 670)
                            if raw_k > 10000: raw_k /= 1000
                            return m.group(1), raw_k

                        typ_s, k_s = parse_k(short_sym)
                        typ_l, k_l = parse_k(long_sym)
                        
                        label_prefix = "SPREAD"
                        is_credit = False
                        is_call = (typ_s == 'C')
                        
                        if typ_s == 'C':
                            if k_l < k_s: label_prefix = "DEBIT CALL"
                            else: label_prefix = "CREDIT CALL"; is_credit = True
                        else:
                            if k_l > k_s: label_prefix = "DEBIT PUT"
                            else: label_prefix = "CREDIT PUT"; is_credit = True
                            
                        strikes_str = f"{k_s:.1f}/{k_l:.1f}" if is_credit else f"{k_l:.1f}/{k_s:.1f}"
                        
                        # Stop Logic (Visual Only)
                        stop_lvl = 0.0
                        if is_credit:
                            stop_lvl = k_s + 0.5 if not is_call else k_s - 0.5 # Rough Defense
                        else:
                            stop_lvl = k_l * 0.99 if is_call else k_l * 1.01
                            
                        # Exposure
                        equity = self.account_metrics.get("equity", 1)
                        exposure_pct = (val_net / equity * 100) if equity > 0 else 0
                        exp_style = "bold cyan" if exposure_pct > 5 else "cyan"

                        table.add_row(
                            label_prefix, strikes_str, dte_str, str(qty), 
                            Text(pl_str, style="bold green" if pl_net > 0 else "bold red"), 
                            Text(f"{exposure_pct:.1f}%", style=exp_style),
                            f"{stop_lvl:.2f}", 
                            Text("ARMED", style="bold green")
                        )
                        
                        # INTERNAL SYNC for Auto-Manager
                        self.managed_spreads[long_sym] = {
                            "long_sym": long_sym, "short_sym": short_sym,
                            "long_strike": k_l, "short_strike": k_s,
                            "qty": qty, "avg_price": cost_basis, 
                            "is_call": is_call, "is_credit": is_credit
                        }
                        
                    except Exception as e:
                        self.log_msg(f"Parse Error {short_sym}: {e}")


    async def account_data_loop(self):
        while True:
            await asyncio.sleep(0.5)
            try:
                # Use poll to prevent blocking the async loop entirely
                if await self.acct_sock.poll(100):
                    topic, msg = await self.acct_sock.recv_multipart()
                    import json
                    data = json.loads(msg)
                    positions = data.get("positions", [])
                    
                    # DEBUG LOGGING (Can remove later)
                    if positions:
                        self.log_msg(f"Recv {len(positions)} positions.")
                        p0 = positions[0]
                        ts = p0.get("Timestamp") or p0.get("DateAcquired") or p0.get("Created")
                        if not ts:
                            self.log_msg(f"⚠️ MISSING TS! Keys: {list(p0.keys())}")
                    else:
                        pass

                    eq = float(data.get("total_account_value", 0))
                    self.account_metrics["equity"] = eq
                    pl = sum([float(p.get("UnrealizedProfitLoss", 0)) for p in positions])
                    pl_pct = (pl / eq * 100) if eq != 0 else 0.0
                    self.query_one("#acct_display").update(f"P/L: ${pl:.0f} ({pl_pct:+.1f}%)")
                    self.call_after_refresh(self.update_positions, positions)
            except Exception as e:
                 self.log_msg(f"Acct Loop Err: {e}")
            
    async def fetch_managed_spreads_loop(self):
        while True:
            try:
                reply = await self.robust_send({"cmd": "GET_MANAGED_SPREADS"})
                if reply and reply.get("status") == "ok":
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

    def log_file(self, msg):
        try:
            with open("debug_debit.log", "a") as f:
                f.write(f"{datetime.datetime.now()} {msg}\n")
        except: pass

    async def load_initial_data(self):
        """Loads persistent state on startup (nexus_portfolio.json)."""
        self.log_msg("Loading Initial State (SYNC)...")
        self.log_file("START load_initial_data")
        try:
            import os, json
            path = "nexus_portfolio.json"
            cwd = os.getcwd()
            exists = os.path.exists(path)
            self.log_file(f"CWD: {cwd} | Path: {path} | Exists: {exists}")
            
            if not exists:
                self.log_msg("nexus_portfolio.json NOT FOUND.")
                self.log_file("File not found")
                return

            self.log_file("Opening file...")
            with open(path, "r") as f:
                data = json.load(f)
            self.log_file(f"Loaded JSON. Keys: {list(data.keys())}")
                
            if data:
                if "grouped_positions" in data:
                    count = len(data['grouped_positions'])
                    self.log_msg(f"Loaded Snapshot ({count} groups)")
                    self.log_file(f"Found grouped_positions: {count}")
                    self.populate_from_snapshot(data)
                elif "positions" in data:
                     positions = data.get("positions", [])
                     self.log_msg(f"Loaded Raw Dump ({len(positions)} positions)")
                     self.log_file(f"Found positions: {len(positions)}")
                     self.update_positions(positions)
                else:
                     self.log_msg("Unknown JSON format.")
                     self.log_file("Unknown format")
                
                eq = float(data.get("account_metrics", {}).get("equity", 0)) or float(data.get("total_account_value", 0))
                if eq: self.account_metrics["equity"] = eq
            else:
                self.log_msg("File is empty.")
                self.log_file("Data is empty/None")
                
        except Exception as e:
            self.log_msg(f"Load Error: {e}")
            self.log_file(f"EXCEPTION: {e}")

    def populate_from_snapshot(self, data):
        """Parses Trader Dashboard's 'grouped_positions' format directly."""
        self.log_file("Entering populate_from_snapshot")
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        self.managed_spreads = {}
        
        groups = data.get("grouped_positions", [])
        import re, datetime
        
        for i, g in enumerate(groups):
            try:
                # 1. Parse Basic Info
                strat = g.get("type", "SPREAD")
                qty = int(g.get("qty", 0))
                l_sym = g.get("long_leg")
                s_sym = g.get("short_leg")
                self.log_file(f"Processing group {i}: {strat} {l_sym}/{s_sym}")
                
                # 2. Parse Strikes/Expiry from Symbol (e.g. SPY 260206C715)
                # Helper to extract Strike and Option Type
                def parse_sym(s):
                    # Matches "SPY 260206C715" -> expiry=260206, type=C, strike=715
                    m = re.search(r' (\d{6})([CP])([\d\.]+)$', s)
                    if not m: return None, None, 0.0
                    return m.group(1), m.group(2), float(m.group(3))

                exp, typ_l, k_l = parse_sym(l_sym)
                _, _, k_s = parse_sym(s_sym)
                
                if not exp: 
                    self.log_file(f"Parse failed for {l_sym}")
                    continue 
                
                # 3. DTE
                try:
                    d = datetime.datetime.strptime(exp, "%y%m%d")
                    dte = (d - datetime.datetime.now()).days
                    dte_str = f"{dte}d"
                except: dte_str = "-d"

                # 4. Calculation
                is_credit = "CREDIT" in strat
                is_call = "CALL" in strat
                
                strikes_str = f"{k_s}/{k_l}" if is_credit else f"{k_l}/{k_s}"
                
                # P/L
                pl_pct = g.get("pl_pct", 0.0)
                pl_str = f"{pl_pct:+.1f}%"
                val = float(g.get("net_val", 0))
                
                # Stop Logic (Visual Sync)
                stop_lvl = 0.0
                if is_credit:
                    stop_lvl = k_s + 0.5 if not is_call else k_s - 0.5
                else:
                    stop_lvl = k_l * 0.99 if is_call else k_l * 1.02 # Put 1.02, Call 0.99
                
                # Exposure
                equity = self.account_metrics.get("equity", 1)
                exposure_pct = (val / equity * 100) if equity > 0 else 0.0
                exp_style = "bold cyan" if exposure_pct > 5 else "cyan"

                table.add_row(
                    strat, strikes_str, dte_str, str(qty), 
                    Text(pl_str, style="bold green" if pl_pct > 0 else "bold red"), 
                    Text(f"{exposure_pct:.1f}%", style=exp_style),
                    f"{stop_lvl:.2f}", 
                    Text("ARMED", style="bold green")
                )
                self.log_file(f"Added row {i}")
                
                # Hydrate Manager
                # avg_price is tricky from snapshot. We have net_val and net_pl. 
                # Cost = Val - PL.
                net_pl = float(g.get("net_pl", 0))
                cost = val - net_pl
                
                self.managed_spreads[l_sym] = {
                    "long_sym": l_sym, "short_sym": s_sym,
                    "long_strike": k_l, "short_strike": k_s,
                    "qty": qty, "avg_price": cost, 
                    "is_call": is_call, "is_credit": is_credit
                }
                
            except Exception as e:
                self.log_msg(f"Snap Parse Err: {e}")
                self.log_file(f"Snap Error: {e}")

    # Original on_mount replaced by new logic above
    
    async def market_data_loop(self):
        """Streams SPY price for the 'Defense' stop trigger."""
        while True:
            await asyncio.sleep(0.1)
            try:
                if await self.sub_sock.poll(100):
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
                is_credit = spread.get("is_credit", False)
                
                # Logic Switch
                if is_credit:
                    # CREDIT SPREAD STOP (Defensive)
                    k_short = spread.get("short_strike", 0)
                    if is_call: 
                        # Bear Call: Stop if price rises near Short Strike
                        stop_level = k_short - 0.5
                    else:
                        # Bull Put: Stop if price falls near Short Strike
                        stop_level = k_short + 0.5
                else:
                    # DEBIT SPREAD STOP (Standard)
                    k_long = spread.get("long_strike", 0)
                    if is_call: stop_level = k_long * 0.99
                    else: stop_level = k_long * 1.02
                
                # [NEW] MANUAL STOP OVERRIDE
                manual_stop = self.manual_stops.get(spread.get("long_sym"))
                if manual_stop:
                    try: 
                        stop_level = float(manual_stop)
                        # self.log_msg(f"Using Manual Stop for {spread.get('long_sym')}: {stop_level}")
                    except: pass
                
                # Trigger
                if self.current_spy_price > 0 and stop_level > 0:
                    triggered = False
                    if is_credit:
                        if is_call and self.current_spy_price >= stop_level: triggered = True # Short Call, price Rises
                        if not is_call and self.current_spy_price <= stop_level: triggered = True # Short Put, price Falls
                    else:
                        if is_call and self.current_spy_price <= stop_level: triggered = True # Long Call, price Falls
                        if not is_call and self.current_spy_price >= stop_level: triggered = True # Long Put, price Rises
                    
                    if triggered:
                        # [MODIFIED] Monitor Only - Backend (ts_nexus) now handles execution
                        self.log_msg(f"ðŸ›‘ STOP TRIGGERED: SPY {self.current_spy_price:.2f} hit limit {stop_level:.2f}")
                        self.log_msg("âš ï¸  Handled by Backend Auto-Manager (Monitor Only Mode)")
                        # await self.panic_close_spread(spread, reason="STOP_LOSS")

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
            # [FIX] Backend is slow for GET_CHAIN (20s+). Increase timeout to 45s.
            reply = await self.robust_send(payload, timeout_ms=45000)
            if reply and reply.get("status") == "ok":
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
                if reply: self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Scan Error: {e}")
            
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
            short_sym = parts[0]
            long_sym = parts[1]
            debit = float(parts[2])
            l_strike = float(parts[3]) 
            s_strike = float(parts[4])
            width = float(parts[5])

            # [FIX] Populate selected_spread for Execution Logic
            self.selected_spread = {
                "short_sym": short_sym,
                "long_sym": long_sym,
                "debit": debit,
                "width": width,
                "long_strike": l_strike,
                "short_strike": s_strike
            }

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
            # Update Stop Trigger (Price Level is constant)
            try:
                is_call = l_strike < s_strike
                stop_price = l_strike * 0.99 if is_call else l_strike * 1.01
                # Populate Input with default, allows manual edit
                self.query_one("#stop_trigger_input", Input).value = f"{stop_price:.2f}"
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
            
            
            # Target is 50% of Debit (Fixed)
            total_target = (total_cost * 0.50)
            
            # Update Labels
            self.query_one("#lbl_debit", Static).update(f"${total_cost:,.2f}")
            self.query_one("#lbl_profit", Static).update(f"${total_target:,.2f}")

    @on(Input.Changed, "#qty_input")
    def on_qty_change(self, event):
        self.recalc_totals()

    @on(Button.Pressed, "#execute_btn")
    async def execute_trade(self):
        btn = self.query_one("#execute_btn", Button)
        if btn.disabled: return # Safety check
        btn.disabled = True
        btn.label = "SENDING..." 

        try:
            if not self.selected_spread: 
                btn.disabled = False
                btn.label = "BUY SPREAD"
                return

            qty_val = self.query_one("#qty_input").value
            qty = int(qty_val) if qty_val else 1
            
            self.log_msg(f"Buying {qty}x Spreads...")
            self.log_file(f"Buying {qty}x Spreads...") 
            
            # Send to Backend - SMART WALKER (Limit + Slippage)
            # Revert to LIMIT to use Smart Walker with Cap
            max_slippage = 0.05
            try: max_slippage = float(self.query_one("#slip_input", Input).value)
            except: pass
            
            self.log_msg(f"⚡ [TRACE] SENDING EXECUTE_SPREAD (Side: BUY) [SLIP: {max_slippage}]")
            payload = {
                "cmd": "EXECUTE_SPREAD",
                "side": "BUY",
                "long_sym": self.selected_spread["long_sym"],
                "short_sym": self.selected_spread["short_sym"],
                "qty": qty,
                "price": self.selected_spread["debit"], 
                "order_type": "MARKET", # [TEMP] Force Market to bypass Walker Rejections
                "max_slippage": max_slippage
            }
            self.log_file(f"Payload: {payload}")

            # [NEW] SAVE MANUAL STOP
            try:
                stop_val = self.query_one("#stop_trigger_input").value
                if stop_val:
                    long_sym = self.selected_spread["long_sym"]
                    self.manual_stops[long_sym] = float(stop_val)
                    self.save_stops() # Persist
                    self.log_msg(f"Armed Manual Stop for {long_sym} at {stop_val}")
            except Exception as e:
                self.log_msg(f"Stop Save Error: {e}")
            
            reply = await self.robust_send(payload)
            if reply: 
                self.log_msg(f"Order: {reply.get('msg')}")
                self.log_file(f"Reply: {reply}")
                
        except Exception as e:
            self.log_msg(f"CRASH AV: {e}")
            self.log_file(f"CRASH EXEC: {e}")
            import traceback
            self.log_file(traceback.format_exc())
            
        finally:
            # Re-enable after delay to prevent rapid-fire
            btn.label = "BUY SPREAD"
            btn.disabled = False

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
            "cmd": "CLOSE_SPREAD", 
            "short_sym": target_spread['short_sym'],
            "long_sym": target_spread['long_sym'],
            "qty": int(p['qty']),
            "side": close_side 
        }
        
        try:
            reply = await self.robust_send(payload)
            if reply and reply.get("status") == "ok":
                self.log_msg(f"Close Order Sent! ID: {reply.get('order_id')}")
            else:
                if reply: self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Close Error: {e}")

    async def panic_close_spread(self, spread, reason="STOP_LOSS"):
        """
        Directly closes a spread from the Auto-Manager loop.
        Arg: spread (dict) - The managed spread object.
        """
        self.log_msg(f"⚠ PANIC CLOSE ({reason}): {spread.get('long_strike')}/{spread.get('short_strike')}")
        
        # Determine Side
        # Our Entry was "SELL" (Credit structure matching Debit Spread legs).
        # So we tell ts_nexus to CLOSE the "SELL" side.
        
        close_side = "SELL"
        
        payload = {
            "cmd": "CLOSE_SPREAD", 
            "short_sym": spread['short_sym'],
            "long_sym": spread['long_sym'],
            "qty": int(spread.get('qty', 1)),
            "side": close_side 
        }
        
        try:
            reply = await self.robust_send(payload)
            if reply: 
                 if reply.get("status") == "ok":
                     self.log_msg(f"Panic Close Sent! Msg: {reply.get('msg')}")
                 else:
                     self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Panic Connection Error: {e}")

    def log_msg(self, msg):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        try: self.query_one("#activity_log", Log).write(f"[{t}] {msg}")
        except: pass

    def log_file(self, msg):
        """Writes to debug_debit.log for persistence."""
        t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        try:
            with open("debug_debit.log", "a") as f:
                f.write(f"{t} {msg}\n")
        except: pass

    async def load_stops(self):
        """Loads manual stops from JSON."""
        try:
            import json, os
            if os.path.exists("nexus_debit_stops.json"):
                with open("nexus_debit_stops.json", "r") as f:
                    self.manual_stops = json.load(f)
                self.log_msg(f"Loaded {len(self.manual_stops)} Manual Stops.")
        except Exception as e:
            self.log_msg(f"Load Stops Error: {e}")

    def save_stops(self):
        """Saves manual stops to JSON."""
        try:
            import json
            with open("nexus_debit_stops.json", "w") as f:
                json.dump(self.manual_stops, f, indent=2)
        except Exception as e:
            self.log_msg(f"Save Stops Error: {e}")

if __name__ == "__main__":
    DebitSniperApp().run()