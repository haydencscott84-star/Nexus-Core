# FILE: trader_dashboard.py
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static, Log, Header, Footer, Button, Input, Label
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual import work, on
from rich.text import Text
import zmq, zmq.asyncio, json, datetime, asyncio, re, time, pytz, requests
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try: from tradestation_explorer import TradeStationManager
except: pass
try: from nexus_config import is_sleep_mode
except: is_sleep_mode = lambda: False

# --- CONFIG ---
ZMQ_PORT_MARKET = 5555; ZMQ_PORT_ACCOUNT = 5566
ZMQ_PORT_EXEC = 5567; ZMQ_PORT_CONTROL = 5568; ZMQ_PORT_OPTION_TICK = 5569; ZMQ_PORT_LOGS = 5572
LISTEN_PORTS = [5557, 5558, 5560, 5561, 5563, 5580] # Added 5580 for Hunter Bridge
LOCAL_IP = "127.0.0.1"
ALLOW_IMMEDIATE_TRIGGER = False # Safety: Block immediate triggers in Live Mode
DEFAULT_SLIPPAGE = 0.05

TABLE_COLS = ("EXPIRY", "DTE", "CONTRACT", "PREMIUM", "VOL", "OI", "V/OI", "P/C(Vol)", "P/C(OI)", "MKT($)", "THEO($)", "EDGE", "CONFIDENCE", "BE($)", "WIN%")

def _to_float(v):
    try:
        if v is None: return 0.0
        return float(v.replace(',', '')) if isinstance(v, str) else float(v)
    except: return 0.0

import uuid

def antigravity_dump(filename, data_dictionary):
    """
    Atomically dumps data to a JSON file.
    Writes to a unique temp file first, then renames to prevent read/write collisions.
    Blocking version - use run_in_executor for async.
    """
    temp_file = f"{filename}.{uuid.uuid4()}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
    except Exception as e:
        print(f"State Dump Error: {e}")
        try: os.remove(temp_file)
        except: pass

async def async_antigravity_dump(filename, data):
    """Async wrapper for antigravity_dump"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, antigravity_dump, filename, data)

def parse_position_details(p):
    s = p.get('Symbol', '???'); exp = "-"; typ = "?"; dte_raw = 0
    if p.get('ExpirationDate'):
        try:
            d = datetime.datetime.fromisoformat(p['ExpirationDate'].replace('Z', '+00:00'))
            now = datetime.datetime.now(d.tzinfo); days = (d.date() - now.date()).days
            exp = f"{d.strftime('%b %d')} ({days}d)"
            dte_raw = days
        except: pass
    try:
        m = re.search(r'([CP])0*(\d+(?:\.\d+)?)$', s)
        if m and "OPTION" in str(p.get('AssetType','')).upper():
            k = float(m.group(2)); k = k/1000 if k>10000 and "." not in m.group(2) else k
            return f"{s.split()[0]} {k:g}{m.group(1)}", exp, m.group(1), dte_raw
        return s.split()[0], "SHARES", "S", 0
    except: return s[:8], exp, "?", 0

def fmt_row(r):
    edge = r.get('edge', 0); voi = r.get('voi_ratio', 0)
    edge_style = "bold green" if edge > 1.5 else ("bold red" if edge < -1.5 else "dim white")
    voi_style = "bold #FFD700" if voi < 10 else "bold #FFA500"
    return (
        r.get('exp','-'), str(r.get('dte','-')), 
        Text(f"${r.get('stk',0):.0f} {r.get('type','?')}", style="bold green" if r.get('type')=='CALL' else "bold red"), 
        f"${r.get('prem',0)/1e6:.1f}M" if r.get('prem',0) >= 1e6 else f"${r.get('prem',0)/1e3:.0f}K", str(r.get('vol',0)), str(r.get('oi',0)), Text(f"{voi:.1f}x", style=voi_style), 
        f"{r.get('pc_ratio_vol',0):.2f}", f"{r.get('pc_ratio_oi',0):.2f}", f"{r.get('mkt',0):.2f}", f"{r.get('theo',0):.2f}", 
        Text(f"{edge:+.1f}%", style=edge_style), r.get('conf','MID').replace('🟢 ','').replace('🔴 ','').replace('⚪ ',''), f"{r.get('be',0):.2f}", "-"
    )

class Metric(Static):
    def __init__(self, label, id=None): super().__init__("", id=id); self.label = label
    def on_mount(self): self.update(Text.from_markup(f"[dim]{self.label}:[/] ---"))
    def update_val(self, v, c="white"): self.update(Text.from_markup(f"[dim]{self.label}:[/] [bold {c}]{v}[/]"))

class ExecutionPanel(Static):
    active = reactive(False); sym = reactive(""); price = reactive(0.0); und_price = reactive(0.0)
    market_bid = reactive(0.0); market_ask = reactive(0.0)
    stk = reactive(0.0); typ = reactive("c"); dte = reactive(0.0); occ_sym = reactive(None); vol = reactive(0)
    qty = reactive(1); side = reactive(None); pos_sym = reactive(None)
    stop = reactive(0.0); take = reactive(0.0); take_2 = reactive(0.0); take_3 = reactive(0.0); armed = reactive(False)
    pending_confirmation = reactive(False)
    
    def compose(self):
        yield Label("WAITING...", id="lbl-desc")
        yield Label("Mkt: $--.--", id="lbl-price")
        
        with Horizontal(classes="row-sm"): 
            for x in [1,5,10]: yield Button(str(x), id=f"btn-q{x}", classes="btn-q")
            
        with Horizontal(classes="row-md"):
            yield Button("BUY", id="btn-buy", variant="success", disabled=True)
            yield Button("SELL", id="btn-sell", variant="error", disabled=True)
            
        with Horizontal(classes="row-sm"):
            yield Label("Limit $:", classes="lbl-xs")
            yield Input(id="inp-limit", classes="inp-xs", placeholder="Mid")
            
        yield Button("EXECUTE", id="btn-exec", variant="primary", disabled=True)
        yield Button("CANCEL ORDER", id="btn-cancel", variant="error")
        
        yield Label("--- AUTO MGR (SPY) ---", classes="hdr")
        with Horizontal(classes="row-sm"): 
            yield Label("S/L:", classes="lbl-xs"); yield Input(id="inp-sl", classes="inp-xs")
        with Horizontal(classes="row-sm"): 
            yield Label("T1:", classes="lbl-compact"); yield Input(id="inp-pt", classes="inp-compact")
            yield Label("T2:", classes="lbl-compact"); yield Input(id="inp-pt2", classes="inp-compact")
            yield Label("T3:", classes="lbl-compact"); yield Input(id="inp-pt3", classes="inp-compact")
        with Horizontal(classes="row-sm"):
            yield Button("⚪ CLICK TO ARM", id="btn-arm", variant="default", disabled=True)
            yield Button("CLR", id="btn-clear", variant="default", disabled=False)

    def on_mount(self): self.query_one("#btn-q1").variant = "primary"

    def calculate_stagger(self, total_qty):
        if total_qty < 1: return [0, 0, 0]
        if total_qty == 1: return [1, 0, 0]
        if total_qty == 2: return [1, 1, 0]
        
        base = total_qty // 3
        remainder = total_qty % 3
        
        q1 = base + (1 if remainder >= 1 else 0)
        q2 = base + (1 if remainder == 2 else 0)
        q3 = base
        return [q1, q2, q3]

    @on(Button.Pressed, "#btn-clear")
    def do_clear(self):
        # 1. Check if an order is selected to be dismissed
        if self.app.selected_order_id:
            oid = self.app.selected_order_id
            self.app.dismissed_orders.add(oid)
            try:
                self.app.query_one("#tbl-ord", DataTable).remove_row(oid)
                self.app.log_msg(f"Dismissed Order {oid} from view.")
            except: pass
            self.app.selected_order_id = None
            self.app.query_one("#btn-cancel").styles.display = "none"
            return

        # 2. Normal Input Clear
        self.stop = 0.0; self.take = 0.0; self.take_2 = 0.0; self.take_3 = 0.0
        self.query_one("#inp-sl", Input).value = ""
        self.query_one("#inp-pt", Input).value = ""
        self.query_one("#inp-pt2", Input).value = ""
        self.query_one("#inp-pt3", Input).value = ""
        self.reset_trigger()

    @on(Button.Pressed, "#btn-arm")
    def toggle_arm(self):
        btn = self.query_one("#btn-arm")
        if "ARMED" in str(btn.label): self.reset_trigger(); return
        if not self.pos_sym: return
        
        # Validate Inputs
        try:
            sl_val = self.query_one("#inp-sl", Input).value.strip()
            pt1_val = self.query_one("#inp-pt", Input).value.strip()
            pt2_val = self.query_one("#inp-pt2", Input).value.strip()
            pt3_val = self.query_one("#inp-pt3", Input).value.strip()
            
            self.stop = float(sl_val) if sl_val else 0.0
            self.take = float(pt1_val) if pt1_val else 0.0
            self.take_2 = float(pt2_val) if pt2_val else 0.0
            self.take_3 = float(pt3_val) if pt3_val else 0.0
            
            if self.stop == 0 and self.take == 0 and self.take_2 == 0 and self.take_3 == 0:
                self.app.log_msg("[bold red]⚠ Cannot Arm: Set S/L or P/T[/]")
                return
        except ValueError:
            self.app.log_msg("[bold red]⚠ Invalid Number Format[/]")
            return
        
        if not self.armed:
            p = self.und_price
            if p <= 0: 
                self.app.log_msg("[yellow]⚠ Warning: Arming with stale/fallback price[/]")
            else:
                # PRE-FLIGHT CHECK: Prevent Immediate Trigger
                immediate_trigger = False
                reason = ""
                
                # Check Stop
                if self.typ.upper().startswith('C'):
                    if self.stop > 0 and p <= self.stop: immediate_trigger=True; reason=f"Price ${p:.2f} <= Stop ${self.stop}"
                else:
                    if self.stop > 0 and p >= self.stop: immediate_trigger=True; reason=f"Price ${p:.2f} >= Stop ${self.stop}"
                
                # Check Targets (Any immediate hit?)
                for t_val in [self.take, self.take_2, self.take_3]:
                    if t_val > 0:
                        if self.typ.upper().startswith('C'):
                             if p >= t_val: immediate_trigger=True; reason=f"Price ${p:.2f} >= Target ${t_val}"
                        else:
                             if p <= t_val: immediate_trigger=True; reason=f"Price ${p:.2f} <= Target ${t_val}"
                
                if immediate_trigger:
                    if not self.pending_confirmation:
                        self.app.log_msg(f"[bold yellow]⚠ IMMEDIATE TRIGGER: {reason}[/]")
                        self.app.log_msg("[yellow]Click again to CONFIRM execution[/]")
                        self.pending_confirmation = True
                        btn.variant = "warning"
                        btn.label = "⚠️ CONFIRM?"
                        return
                    else:
                        self.app.log_msg(f"[bold red]⛔ CONFIRMED IMMEDIATE TRIGGER: {reason}[/]")
                        self.pending_confirmation = False

            self.armed = True; btn.variant = "error"; btn.label = "🚨 ARMED 🚨"
            
            # Calculate Stagger
            qty_total = self.app.pos_map[self.pos_sym]['qty'] if self.pos_sym in self.app.pos_map else self.qty
            q1, q2, q3 = self.calculate_stagger(qty_total)
            
            # Smart Rollback Logic
            t1_price = self.take
            t2_price = self.take_2
            t3_price = self.take_3
            
            # If T3 is empty, move its shares to T2 (or T1 if T2 is also empty)
            if t3_price <= 0:
                if t2_price > 0: q2 += q3
                else: q1 += q3
                q3 = 0

            # If T2 is empty, move its shares to T1
            if t2_price <= 0:
                q1 += q2
                q2 = 0
            
            targets = []
            if t1_price > 0 and q1 > 0: targets.append({'price': t1_price, 'qty': q1, 'id': 1})
            if t2_price > 0 and q2 > 0: targets.append({'price': t2_price, 'qty': q2, 'id': 2})
            if t3_price > 0 and q3 > 0: targets.append({'price': t3_price, 'qty': q3, 'id': 3})
            
            # 1. Local State & Sync (Unified)
            self.app.oco[self.pos_sym] = {
                'stop': self.stop, 
                'targets': targets, 
                'type': self.typ
            }
            self.app.save_oco()
            
            t_str = f"T1:{self.take}"
            if self.take_2 > 0: t_str += f" T2:{self.take_2}"
            if self.take_3 > 0: t_str += f" T3:{self.take_3}"
            self.app.log_msg(f"[UI] Arming {self.pos_sym} S/L:{self.stop} {t_str}")
            
            # 3. Server Broadcast (ARM command payload needs update or just rely on local triggering?)
            # The original code sent "ARM" with stop/take.
            # Since we are moving to multi-target, the server might not support it yet.
            # But the user instruction said: "Update the Arming Logic (toggle_arm)... Save to OCO".
            # It didn't explicitly say to update the server payload structure, but the server might need to know.
            # However, the monitoring loop (sub_mkt) is LOCAL in this dashboard.
            # So as long as we update sub_mkt, we are good.
            # The "ARM" command sent to server is likely for the *other* backend (Guardian/Nexus).
            # If that backend doesn't support list of targets, we might have issues if IT triggers exits.
            # But the prompt says "PART 3 B: The Monitoring Loop (sub_mkt)... Update the loop".
            # This implies the Dashboard is doing the monitoring.
            # So I will send a simplified ARM command or just the first target?
            # Or maybe just send the STOP to the server as a safety net?
            # I'll send the STOP and maybe the first TAKE as a proxy, but rely on local for staggered.
            # 3. Server Broadcast
            qty_to_arm = qty_total
            self.app.run_worker(self.app.send_order("ARM", str(qty_to_arm), self.pos_sym, stop=self.stop, take=self.take, targets=targets, type=self.typ))
            
        else: 
            self.reset_trigger()

    def reset_trigger(self):
        self.armed = False; self.pending_confirmation = False
        self.query_one("#btn-arm").variant = "default"; self.query_one("#btn-arm").label = "⚪ CLICK TO ARM"
        
        # 1. Local Clear
        if self.pos_sym and self.pos_sym in self.app.oco: del self.app.oco[self.pos_sym]; self.app.save_oco()
        
        # 2. Server Broadcast (THE FIX)
        if self.pos_sym:
            self.app.run_worker(self.app.send_order("DISARM", "0", self.pos_sym))

    def watch_price(self, val):
        self.query_one("#lbl-price").update(f"Mkt: ${val:.2f}")
        # [FIX] Do NOT auto-fill limit input here. It prevents user from clearing it for MARKET orders.
        # The input is already seeded in load_contract.
            
    def watch_sym(self, val):
        desc = f"${self.stk:.0f} {self.typ} ({self.dte:.0f}d)" if val else "WAITING..."
        self.query_one("#lbl-desc").update(desc)
        self.query_one("#btn-buy").disabled = not val; self.query_one("#btn-sell").disabled = not val
        self.side=None
        
    def watch_side(self, val):
        self.query_one("#btn-exec").disabled = (val is None) or self.active
        
    def watch_qty(self, val):
        for x in [1,5,10]: self.query_one(f"#btn-q{x}").variant = "primary" if x==val else "default"
        if self.side: self.watch_side(self.side)

    def watch_pos_sym(self, s):
        self.query_one("#btn-arm").disabled = not s
        if not s: self.armed=False; self.query_one("#btn-arm").variant="default"; self.query_one("#btn-arm").label="⚪ CLICK TO ARM"
        
    @on(Input.Changed)
    def on_inp(self, e):
        try:
            v = float(e.value)
            if e.input.id=="inp-sl": self.stop=v
            elif e.input.id=="inp-pt": self.take=v
            elif e.input.id=="inp-pt2": self.take_2=v
            elif e.input.id=="inp-pt3": self.take_3=v
            
            self.pending_confirmation=False
            if self.armed:
                 # If modification while armed, we should probably disarm or warn.
                 # For now, just update local state if safe?
                 # Actually, re-arming is safer.
                 self.query_one("#btn-arm").label="⚪ RE-ARM"
                 self.query_one("#btn-arm").variant="warning"
                 self.armed = False # Force re-arm to recalculate stagger
        except: pass
        
    @on(Button.Pressed, ".btn-q")
    def set_qty(self, e): self.qty = int(e.button.label.plain)
    @on(Button.Pressed, "#btn-buy")
    def set_buy(self): self.side="BUY"
    @on(Button.Pressed, "#btn-sell")
    def set_sell(self): self.side="SELL"
    
    @on(Button.Pressed, "#btn-exec")
    def do_exec(self): 
        lim_val = self.query_one("#inp-limit", Input).value.strip()
        # MARKET if empty, LIMIT if text
        if lim_val:
            try: limit_price = float(lim_val)
            except: limit_price = self.price 
        else: limit_price = None

        # [FIX] Defensive Symbol Check
        exec_sym = self.sym
        # Always prefer OCC Symbol if available (Canonical Source)
        if self.occ_sym and len(self.occ_sym) > 8:
            exec_sym = self.occ_sym
        elif self.occ_sym and (len(self.sym) < 6 or " " not in self.sym):
             # Fallback if regular sym is malformed
             exec_sym = self.occ_sym

        self.app.log_msg(f"DEBUG EXEC: {self.side} {self.qty} {exec_sym} L:{limit_price}")
        self.app.run_worker(self.app.send_order(self.side, str(self.qty), exec_sym, limit_price=limit_price))
        self.side=None

class TraderDashboardV2(App):
    CSS = """
    Screen { background: $surface; }
    #hdr { dock: top; height: 8; background: $surface-darken-1; border-bottom: solid $primary; layout: grid; grid-size: 5; grid-rows: 1fr 1fr; grid-columns: 1fr 1fr 1fr 1fr 1fr; }
    Metric { width: 100%; height: 100%; content-align: center middle; border: solid $primary-darken-2; }
    #exec-panel { dock: right; width: 46; height: 100%; border-left: solid $primary; background: $surface-darken-1; padding: 0 1; overflow-y: auto; }
    #left-pane { width: 1fr; height: 100%; }
    #tbl-con { height: 50%; border-bottom: solid $primary-darken-1; }
    #tbl-pos { height: 25%; border-bottom: solid $primary-darken-1; }
    #tbl-ord { height: 1fr; border-top: solid $secondary; }
    .lbl-sm { margin-top: 1; color: $text-muted; }
    .row-sm { height: 3; margin-bottom: 1; align: center middle; }
    .row-md { height: 5; margin-bottom: 1; align: center middle; }
    .btn-q { width: 1fr; min-width: 6; } 
    #btn-buy { width: 48%; height: 100%; background: #008000; color: white; }
    #btn-sell { width: 48%; height: 100%; background: #D90429; color: white; }
    #btn-sell { width: 48%; height: 100%; background: #D90429; color: white; }
    #btn-exec { width: 100%; height: 3; border: solid $secondary; }
    #btn-cancel { width: 100%; height: 3; background: #BF616A; color: white; margin-top: 1; display: none; }
    .hdr { text-align: center; background: $surface-darken-2; color: $secondary; margin-top: 1; }
    .lbl-xs { width: 8; content-align: right middle; padding-right: 1; }
    .inp-xs { width: 1fr; height: 3; border: none; background: $surface-darken-2; }
    .lbl-xs { width: 8; content-align: right middle; padding-right: 1; }
    .inp-xs { width: 1fr; height: 3; border: none; background: $surface-darken-2; }
    .lbl-compact { width: 3; content-align: right middle; padding-right: 0; color: $text-muted; }
    .inp-compact { width: 1fr; height: 3; border: none; background: $surface-darken-2; margin-right: 1; }
    #btn-clear { width: 30%; height: 100%; background: #BF616A; color: white; margin-left: 1; }
    #btn-arm { width: 68%; height: 100%; }
    #event_log { dock: bottom; height: 10; background: $surface-darken-2; border-top: solid $secondary; overflow-y: scroll; }
    """
    zmq_ctx = zmq.asyncio.Context(); oco = {}; pos_map = {}; contract_map = {}
    current_regime = reactive("NEUTRAL")
    dismissed_orders = set()
    selected_order_id = None
    last_acct_update = 0
    last_mkt_update = 0

    def compose(self):
        yield Header(show_clock=False)
        with Container(id="hdr"):
            # ROW 1
            yield Metric("ACCT", id="m-acct")
            yield Metric("SIG", id="m-sig")
            yield Metric("EXP", id="m-exp")
            yield Metric("P/L", id="m-pl")
            yield Metric("SYSTEM", id="m-system")
            yield Metric("SPY", id="m-spy")
            yield Metric("OPT.Δ", id="m-opt-delta")
            yield Metric("FUT.Δ", id="m-fut-delta")
            yield Metric("PORT.Δ", id="m-port-delta")
            yield Metric("GAMMA | THETA", id="m-gamma") 
        with Container():
            yield ExecutionPanel(id="exec-panel")
            with Vertical(id="left-pane"):
                yield DataTable(id="tbl-con")
                yield DataTable(id="tbl-pos")
                yield DataTable(id="tbl-ord")
        yield Log(id="event_log", highlight=True); yield Footer()

    def log_msg(self, t): 
        msg = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {t}"
        self.query_one(Log).write(msg)
        try:
            with open("dashboard_debug.log", "a") as f: f.write(msg + "\n")
        except: pass

    def update_clock(self):
        try: self.query_one(Header).query_one(Clock).update(datetime.datetime.now().strftime("%H:%M:%S"))
        except: pass

    async def on_mount(self):
        self.query_one("#tbl-con", DataTable).add_columns(*TABLE_COLS); self.query_one("#tbl-con", DataTable).cursor_type = "row"
        t = self.query_one("#tbl-pos", DataTable)
        t.add_columns("CONTRACT", "EXP", "QTY", "VAL", "P/L", "AGE", "STOP", "T1", "T2", "T3")
        t.cursor_type = "row"
        
        # ORDERS TABLE
        to = self.query_one("#tbl-ord", DataTable)
        to.add_columns("ID", "SYMBOL", "SIDE", "QTY", "TYPE", "PRICE", "STATUS")
        to.cursor_type = "row"
        
        # self.load_oco() # [REMOVED] Handled by async_load_oco in on_ready

    async def async_load_oco(self):
        """Async Load OCO from disk."""
        loop = asyncio.get_event_loop()
        def _read():
            try: 
                if os.path.exists("active_targets.json"):
                    with open("active_targets.json") as f: return json.load(f)
            except: pass
            return {}
        
        data = await loop.run_in_executor(None, _read)
        if data: self.oco = data

    async def async_save_oco(self):
        """Async Save OCO to disk."""
        loop = asyncio.get_event_loop()
        # Capture state to write (thread safety: minimal risk in asyncio single thread, but good practice)
        data_to_write = self.oco.copy()
        
        def _write():
            try: 
                with open("active_targets.json","w") as f: json.dump(data_to_write, f, indent=4)
            except: pass
            
        await loop.run_in_executor(None, _write)

    # Legacy wrappers acting as bridges if needed, but we should switch calls.
    # For sync event handlers, we use run_worker.
    def save_oco(self):
        self.run_worker(self.async_save_oco())

    async def on_ready(self):
        self.log_msg("--- DASHBOARD V2.2: SERVER SYNC ENABLED ---")
        self.ex = self.zmq_ctx.socket(zmq.REQ); self.ex.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
        self.pub = self.zmq_ctx.socket(zmq.PUB); self.pub.bind(f"tcp://{LOCAL_IP}:{ZMQ_PORT_CONTROL}")
        self.run_worker(self.sub_mkt)
        self.run_worker(self.sub_acct) # [FIX] Start Account Stream
        self.run_worker(self.sub_logs)
        self.run_worker(self.monitor_greeks) # [RESTORED] Greek Monitor
        self.run_worker(self.pulse_heartbeat) # Added Pulse
        self.run_worker(self.sub_strat_hud) # Safety Bridge
        self.run_worker(self.sub_sel); self.run_worker(self.sub_option_tick); self.run_worker(self.sub_logs)
        self.run_worker(self.sub_ts_stream) # [NEW] Real-time TS Quotes
        self.run_worker(self.fetch_open_orders) # [NEW] Open Orders Polling
        self.run_worker(self.sync_oco_worker) # [NEW] Background File Sync
        self.set_interval(1.0, self.update_clock)
        
        # Initial Load
        self.run_worker(self.async_load_oco())

    async def sync_oco_worker(self):
        """Background worker to sync OCO file without blocking UI."""
        while True:
            try:
                await self.async_load_oco()
            except Exception as e:
                self.log_msg(f"Sync Err: {e}")
            await asyncio.sleep(2.0) # Poll every 2s, safely away from market loop

    @on(DataTable.RowSelected, "#tbl-con")
    def on_con_click(self, e):
        sym = e.row_key.value
        if sym in self.contract_map: self.load_contract(self.contract_map[sym])
        self.update_safety_lock()

    @on(DataTable.RowSelected, "#tbl-pos")
    def on_pos_click(self, e):
        if e.row_key.value in self.pos_map:
            d = self.pos_map[e.row_key.value]
            xp = self.query_one(ExecutionPanel)
            xp.sym = d['sym']; xp.stk = d['stk']; xp.dte = d['dte']; xp.typ = d['typ']; xp.price = d['mkt']; xp.pos_sym = d['sym']
            xp.qty = int(d['qty']); xp.side = "SELL"
            xp.watch_sym(xp.sym); xp.watch_price(xp.price); xp.watch_qty(xp.qty)
            xp.query_one("#inp-limit", Input).value = f"{d['mkt']:.2f}"
            if d['sym'] in self.oco:
                r = self.oco[d['sym']]
                xp.stop = r.get('stop', 0)
                xp.query_one("#inp-sl", Input).value = str(xp.stop)
                
                # Load Targets
                targets = r.get('targets', [])
                # Reset inputs first
                xp.query_one("#inp-pt", Input).value = ""
                xp.query_one("#inp-pt2", Input).value = ""
                xp.query_one("#inp-pt3", Input).value = ""
                
                for t in targets:
                    tid = t.get('id', 1)
                    if tid == 1: xp.query_one("#inp-pt", Input).value = str(t['price'])
                    elif tid == 2: xp.query_one("#inp-pt2", Input).value = str(t['price'])
                    elif tid == 3: xp.query_one("#inp-pt3", Input).value = str(t['price'])
                
                xp.armed=True; xp.query_one("#btn-arm").variant="warning"; xp.query_one("#btn-arm").label="⚠️ ARMED"
            else:
                xp.armed=False; xp.query_one("#btn-arm").variant="default"; xp.query_one("#btn-arm").label="⚪ CLICK TO ARM"
            self.pub.send_multipart([b"SUB", d['sym'].encode()])
            self.log_msg(f"Locked: {d['desc']}")
            self.update_safety_lock()

    async def sub_strat_hud(self):
        """Safety Bridge: Listen to Strategic HUD for Traps"""
        s = self.zmq_ctx.socket(zmq.SUB)
        try:
            s.connect(f"tcp://{LOCAL_IP}:5559")
            s.subscribe(b"STRAT_HUD")
            self.log_msg("Safety Bridge: Connected to HUD")
            while True:
                if await s.poll(1000):
                    msg = await s.recv_multipart()
                    data = json.loads(msg[1].decode('utf-8'))
                    
                    # Update Regime and Trigger Lock Check
                    self.current_regime = data.get('regime', 'NEUTRAL')
                    self.update_safety_lock()
                        
                else: await asyncio.sleep(1)
        except Exception as e: self.log_msg(f"Safety Bridge Err: {e}")

    def update_safety_lock(self):
        """Dynamic Safety Lock: Blocks TRAPPED side only."""
        xp = self.query_one(ExecutionPanel)
        regime = self.current_regime
        
        should_disable = False
        warning_msg = ""
        
        # [DISABLED BY USER REQUEST]
        # 1. BULL TRAP (Market Dropping) -> Block CALLS
        # if "TRAPPED BULLS" in regime or "BEARISH" in regime:
        #     if xp.typ.upper().startswith("C") and xp.side != "SELL": # Allow Sells, Block Buys
        #          should_disable = True
        #          warning_msg = "⛔ TRAP: CALLS LOCKED"

        # 2. BEAR TRAP (Market Ripping) -> Block PUTS
        # elif "TRAPPED BEARS" in regime or "SQUEEZE" in regime:
        #     if xp.typ.upper().startswith("P") and xp.side != "SELL":
        #          should_disable = True
        #          warning_msg = "⛔ TRAP: PUTS LOCKED"
                 
        btn_buy = xp.query_one("#btn-buy")
        if should_disable:
            btn_buy.disabled = True
            btn_buy.label = warning_msg
            btn_buy.variant = "error"
        else:
            # Restore if a symbol is selected
            if xp.sym:
                btn_buy.disabled = False
                btn_buy.label = "BUY"
                btn_buy.variant = "success"

    async def fetch_fallback_price(self):
        """Fetches snapshot from TradeStation if live feed is dead."""
        try:
            # Import Config
            try: from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
            except: return 0.0

            # Run in thread to avoid blocking UI
            loop = asyncio.get_event_loop()
            def _fetch():
                try:
                    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
                    q = ts.get_quote_snapshot("SPY")
                    return float(q.get('Last', 0))
                except: return 0.0
            
            price = await loop.run_in_executor(None, _fetch)
            return float(price)
        except: return 0.0


    async def read_json_async(self, path):
        """Non-blocking JSON file read."""
        if not os.path.exists(path): 
            # self.log_msg(f"DEBUG: File not found: {path}")
            return {}
        loop = asyncio.get_event_loop()
        def _read():
            try:
                with open(path, "r") as f: return json.load(f)
            except Exception as e:
                self.log_msg(f"Read Error {path}: {e}")
                return {}
        return await loop.run_in_executor(None, _read)

    async def pulse_heartbeat(self):
        """Visual Confidence Indicator (The output hasn't frozen). Displays NY Time."""
        while True:
            try:
                # Update the dedicated Metric widget in the top bar
                ny_time = datetime.datetime.now(pytz.timezone('America/New_York'))
                t = ny_time.strftime("%H:%M:%S")
                color = "bold green" if int(time.time()) % 2 == 0 else "dim green"
                # ID is generated as "m-" + "SYSTEM".lower() -> "m-system"
                self.query_one("#m-system", Metric).update_val(f"{t} ⚡", color)
            except: pass
            await asyncio.sleep(1)
            
    async def monitor_greeks(self):
        """Restored: Polls nexus_greeks.json, hedge_state.json for portfolio risk metrics (Async)."""
        await asyncio.sleep(2.0) # [FIX] Allow UI to fully mount before hammering reactives
        self.log_msg("Matcha: Monitor Greeks STARTING (Dedicated Thread)...")
        
        # Dedicated Executor to prevent starvation
        from concurrent.futures import ThreadPoolExecutor
        _g_exec = ThreadPoolExecutor(max_workers=1)
        
        # Persistence State
        last_success_greeks = 0
        last_success_hedge = 0
        
        # [DEBOUNCE STATE]
        last_good_ts = time.time()
        
        p = {
            "opt_delta": 0.0, "opt_gamma": 0.0, "opt_theta": 0.0, "fut_delta": 0.0, "port_total": 0.0
        }
        
        async def _read_p(path):
            if not os.path.exists(path): return {}
            loop = asyncio.get_event_loop()
            def _r():
                try: 
                    with open(path, "r") as f: return json.load(f)
                except: return {}
            return await loop.run_in_executor(_g_exec, _r)

        while True:
            try:
                # 1. Option Greeks (With Timeout)

                valid_greeks = False
                # [FIX] Initialize with PERSISTENT values, not 0.0.
                # This prevents a Read Timeout from being interpreted as "Zero Greeks"
                new_opt_delta = p["opt_delta"]
                new_opt_gamma = p["opt_gamma"]
                new_opt_theta = p["opt_theta"]
                
                try:
                    g_data = await asyncio.wait_for(_read_p("nexus_greeks.json"), timeout=1.5)
                    if g_data and "greeks" in g_data:
                        greeks = g_data["greeks"]
                        new_opt_delta = float(greeks.get("delta", 0))
                        new_opt_gamma = float(greeks.get("gamma", 0))
                        new_opt_theta = float(greeks.get("theta", 0))
                        last_success_greeks = time.time()
                        valid_greeks = True
                except asyncio.TimeoutError:
                    pass # Keep previous values (now correctly initialized from p)
                except Exception:
                    pass

                # 2. Futures Greeks (Hedge)
                valid_hedge = False
                new_fut_delta = p["fut_delta"] # [FIX] Keep persistent
                try:
                    h_data = await asyncio.wait_for(_read_p("hedge_state.json"), timeout=1.5)
                    if h_data:
                        new_fut_delta = float(h_data.get("hedged_delta", 0))
                        last_success_hedge = time.time()
                        valid_hedge = True
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    pass
                
                # 3. Portfolio Totals & Debounce Logic
                new_port_total = new_opt_delta + new_fut_delta
                
                # Check for "Zero Flash"
                is_zero_flash = (abs(new_port_total) < 0.001 and abs(new_opt_gamma) < 0.001)
                
                should_update = True
                
                if not is_zero_flash:
                    # Valid Data -> Update State & Timestamp
                    last_good_ts = time.time()
                    p["opt_delta"] = new_opt_delta
                    p["opt_gamma"] = new_opt_gamma
                    p["opt_theta"] = new_opt_theta
                    p["fut_delta"] = new_fut_delta
                    p["port_total"] = new_port_total
                else:
                    # Zero Data -> Check if we should mask it
                    # If < 3s since last good data, Ignore it (Masking)
                    if time.time() - last_good_ts < 3.0:
                        should_update = False
                    else:
                        # > 3s of zeros -> Real Liquidation -> Allow update
                        p["opt_delta"] = 0.0
                        p["opt_gamma"] = 0.0
                        p["opt_theta"] = 0.0
                        p["fut_delta"] = 0.0
                        p["port_total"] = 0.0
                
                # Color Logic (Dim if Stale > 10s or masked state)
                if should_update:
                    now = time.time()
                    is_stale_g = (now - last_success_greeks) > 10
                    is_stale_h = (now - last_success_hedge) > 10
                    
                    # OPTION DELTA
                    if is_stale_g: od_col = "dim white"
                    else: od_col = "magenta" if p["opt_delta"] > 0 else "#FF5555" 
                    
                    # FUTURES DELTA
                    if is_stale_h: fd_col = "dim white"
                    else: fd_col = "cyan" if p["fut_delta"] > 0 else "#FF5555"

                    # PORTFOLIO DELTA
                    if p["port_total"] == 0 and is_stale_g and is_stale_h:
                         pd_col = "dim white"
                    else:
                         pd_col = "bold green" if p["port_total"] > 0 else "bold red"
                         
                    # GAMMA
                    if is_stale_g: g_col = "dim white"
                    else: g_col = "cyan" if p["opt_gamma"] > 0 else "#FF5555"
                    
                    # THETA
                    if is_stale_g: t_col = "dim white"
                    else: t_col = "green" if p["opt_theta"] > 0 else "#FF5555"
                    
                    # Update Widgets
                    self.query_one("#m-opt-delta", Metric).update_val(f"{p['opt_delta']:+.2f}", od_col)
                    self.query_one("#m-fut-delta", Metric).update_val(f"{p['fut_delta']:+.2f}", fd_col)
                    self.query_one("#m-port-delta", Metric).update_val(f"{p['port_total']:+.2f}", pd_col)
                    
                    gamma_str = f"[{g_col}]{p['opt_gamma']:+.2f}[/]"
                    theta_str = f"[{t_col}]{p['opt_theta']:+.2f}[/]"
                    combined_str = f"{gamma_str} | {theta_str}"
                    self.query_one("#m-gamma", Metric).update_val(combined_str, "white")
                    
                    # Force Refresh (Ensure Repaint)
                    self.refresh()
                        
            except Exception as e:
                self.log_msg(f"GREEK MONITOR ERR: {e}")
            
            await asyncio.sleep(1)

    async def sub_mkt(self):
        s=self.zmq_ctx.socket(zmq.SUB); s.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_MARKET}"); s.subscribe(b"SPY")
        
        # Initial Fallback Fetch
        if not is_sleep_mode():
            self.fallback_price = await self.fetch_fallback_price()
            if self.fallback_price > 0:
                 self.query_one("#m-spy", Metric).update_val(f"${self.fallback_price:.2f} (C)", "#ebcb8b")
                 self.query_one(ExecutionPanel).und_price = self.fallback_price
                 
        # Non-blocking check for loop entry (avoid immediate block)
        while True:
            try:
                if is_sleep_mode():
                    self.query_one("#m-spy", Metric).update_val("SLEEP", "dim white")
                    await asyncio.sleep(60)
                    continue
                
                # Non-blocking check
                if await s.poll(1000):
                    msg=await s.recv_multipart(); d=json.loads(msg[1]); p=_to_float(d.get('Last',0))
                    if p>0: 
                        # THROTTLE UI UPDATES (Max 10 per sec)
                        now = datetime.datetime.now().timestamp()
                        if now - self.last_mkt_update > 0.1:
                            self.query_one("#m-spy", Metric).update_val(f"${p:.2f}", "#ebcb8b")
                            self.last_mkt_update = now
                        
                        self.query_one(ExecutionPanel).und_price = p
                        
                        # LOCAL FALLBACK CHECK (In case server fails)
                        for sym, r in list(self.oco.items()): 
                            stop=r.get('stop',0); otyp=r.get('type','C')
                            
                            # 1. Check Targets (Staggered)
                            if 'targets' in r:
                                for t in r['targets'][:]: # Iterate copy to modify
                                    limit_price = t['price']
                                    qty_to_sell = t['qty']
                                    hit = False
                                    
                                    if otyp.upper().startswith('C') and p >= limit_price: hit = True
                                    elif otyp.upper().startswith('P') and p <= limit_price: hit = True
                                    
                                    if hit:
                                        # TRIGGER EXECUTION (DELEGATE TO NEXUS)
                                        # We send FORCE_EXIT with reason="TAKE" so Nexus uses Smart Exit (Limit @ Mid)
                                        # Do NOT send limit_price here, as it would be the SPY price!
                                        
                                        # Determine Side (Buy to Close if Short, Sell to Close if Long)
                                        side = "SELL"
                                        if sym in self.pos_map:
                                            q = self.pos_map[sym]['qty']
                                            if q < 0: side = "BUY"
                                            
                                        self.run_worker(self.send_order("FORCE_EXIT", str(qty_to_sell), sym, reason="TAKE_Stagger", side=side))
                                        self.log_msg(f"🎯 TARGET HIT: Delegating {qty_to_sell} to Nexus")
                                        r['targets'].remove(t)
                                        self.save_oco()
                            
                            # 2. Check Stop (Global)
                            hit=False; reason=""
                            if otyp.upper().startswith('C'): 
                                if stop>0 and p<=stop: hit=True; reason=f"STOP {stop}"
                            else: 
                                if stop>0 and p>=stop: hit=True; reason=f"STOP {stop}"
                            
                            if hit:
                                del self.oco[sym]; self.save_oco()
                                q=self.pos_map[sym]['qty'] if sym in self.pos_map else 1
                                
                                dte = 0
                                if sym in self.pos_map:
                                    dte = self.pos_map[sym].get('dte', 0)
                                    
                                # Determine Side
                                side = "SELL"
                                if sym in self.pos_map:
                                    q = self.pos_map[sym]['qty']
                                    if q < 0: side = "BUY"
                                
                                self.run_worker(self.send_order("FORCE_EXIT", str(q), sym, reason="STOP", dte=dte, side=side))
                                self.log_msg(f"[bold red]LOCAL TRIGGER {sym}: {reason} (DTE:{dte})[/]")
                else:
                    # No data for 1s, ensure we show fallback if we have nothing else?
                    # Actually, we keep showing the last known price.
                    # But if we started with 0 and poll timed out, we use fallback.
                    if self.query_one(ExecutionPanel).und_price == 0 and self.fallback_price > 0:
                        self.query_one("#m-spy", Metric).update_val(f"${self.fallback_price:.2f} (C)", "#ebcb8b")
                        self.query_one(ExecutionPanel).und_price = self.fallback_price
                        
            except: await asyncio.sleep(1)
            # to prevent UI freezes during disk I/O.



    async def sub_acct(self):
        s=self.zmq_ctx.socket(zmq.SUB); s.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_ACCOUNT}"); s.subscribe(b"A")
        while True:
            try:
                if is_sleep_mode():
                    self.query_one("#m-acct", Metric).update_val("SLEEP", "dim white")
                    await asyncio.sleep(60)
                    continue

                # self.log_msg("Waiting for ACCT...")
                msg=await s.recv_multipart(); d=json.loads(msg[1])
                # DEBUG: Log keys to check for mismatch
                # if int(time.time()) % 10 == 0: self.log_msg(f"DEBUG ACCT KEYS: {list(d.keys())}")
            
                # THROTTLE ACCOUNT UPDATES (Max 1 per sec)
                now = datetime.datetime.now().timestamp()
                if now - self.last_acct_update < 1.0:
                    await asyncio.sleep(0.1)
                    continue
                self.last_acct_update = now

                eq=_to_float(d.get("total_account_value",0))
                val_agg = _to_float(d.get("value_of_open_positions",0))
                pnl_agg = _to_float(d.get("unrealized_pnl",0))
            
                # DEBOUNCE LOGIC (Empty Payload Flicker Prevention)
                # [FIX]: Filter out Qty=0 positions (Zombies/Closed) BEFORE checking for empty
                raw_positions = d.get("positions", [])
                effective_positions = [p for p in raw_positions if abs(float(p.get('Quantity', 0))) > 0.001]
                
                # [NEW] FALSE-EMPTY GUARD (Client Side)
                # If we have significant market value ($500+) but 0 positions, the API likely failed to return positions.
                if not effective_positions and val_agg > 500:
                    # self.log_msg(f"⚠️ IGNORED FALSE EMPTY: Val=${val_agg:.2f} but Pos=0")
                    # Update metrics only, skip table clear
                    self.query_one("#m-acct", Metric).update_val(f"${eq/1000:.1f}k", "#88c0d0")
                    self.query_one("#m-pl", Metric).update_val(f"{pnl_agg:+.0f}", "green" if pnl_agg>=0 else "red")
                    await asyncio.sleep(0.1)
                    continue

                if not effective_positions:
                     # Initialize counter if needed
                     if not hasattr(self, "empty_payload_count"): self.empty_payload_count = 0
                     
                     self.empty_payload_count += 1
                     if self.empty_payload_count < 3: # Increased to 3 frames (~3s)
                         # Ignore first 2 empty frames (Hiccup)
                         await asyncio.sleep(0.1)
                         continue
                else:
                     self.empty_payload_count = 0

                sum_val = 0; sum_pnl = 0
                tbl=self.query_one("#tbl-pos", DataTable)
                
                # DIFF-BASED UPDATE STRATEGY
                seen_keys = set()
                self.pos_map={}
                
                # Statistics for Flicker Debugging
                updates_this_cycle = 0
                
                # Get Column Keys (Robust)
                try: col_keys = list(tbl.columns.keys())
                except: col_keys = []
                
                # --- SPREAD GROUPING ---
                grouped_display, grouped_export, processed_syms = self.group_positions(raw_positions)
                
                # Helper for Change Detection
                def smart_update(k, col_idx, new_val):
                    nonlocal updates_this_cycle
                    if len(col_keys) <= col_idx: return
                    col_k = col_keys[col_idx]
                    try:
                        curr_val = tbl.get_cell(k, col_k)
                        # Compare string representation to avoid type mismatch issues
                        if str(curr_val) != str(new_val):
                            tbl.update_cell(k, col_k, new_val)
                            updates_this_cycle += 1
                    except:
                        # Fallback if get_cell fails
                        tbl.update_cell(k, col_k, new_val)
                        updates_this_cycle += 1

                # 1. Update/Add Grouped Spreads
                for g in grouped_display:
                    k = g['key']
                    seen_keys.add(k)
                    
                    # Columns: CONTRACT, EXP, QTY, VAL, P/L, AGE, STOP, T1, T2, T3
                    vals = (
                        Text(g['label'], style="bold cyan"), 
                        g['exp'], 
                        g['qty'], 
                        f"{g['raw_val']/eq*100:.1f}%" if eq != 0 else "0.0%", 
                        Text(g['pl'], style="green" if g['raw_pl']>=0 else "red"), 
                        g['age'], 
                        "COMBINED", 
                        "COMBINED", 
                        # T2/T3 empty for combined
                        "", ""
                    )
                    
                    if k in tbl.rows:
                        # Update Cells via Column Keys with Smart Check
                        for i in range(10): smart_update(k, i, vals[i])
                    else:
                        tbl.add_row(*vals, key=k)
                        updates_this_cycle += 10 # New row counts as 10 updates

                    sum_val += g['raw_val']
                    sum_pnl += g['raw_pl']

                # 2. Update/Add Individual Positions
                for p in raw_positions:
                    sym=p.get('Symbol')
                    if sym in processed_syms: continue # Skip if part of spread
                    
                    q=int(p.get('Quantity',0)); 
                    if q==0: continue
                    nm, exp, typ, dte_val = parse_position_details(p)
                    mkt_val = _to_float(p.get('MarketValue', 0)); upnl = _to_float(p.get('UnrealizedProfitLoss', 0)); cost = _to_float(p.get('TotalCost', 0))
                    sum_val += mkt_val; sum_pnl += upnl

                    try: stk_val=float(re.search(r"(\d+(?:\.\d+)?)", nm).group(1))
                    except: stk_val=0
                    
                    # --- STOPWATCH (AGE) ---
                    age_str = "?"
                    try:
                        ts_raw = p.get('Timestamp') or p.get('DateAcquired') or p.get('Created')
                        if ts_raw:
                            t_obj = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                            now_obj = datetime.datetime.now(t_obj.tzinfo)
                            diff = now_obj - t_obj
                            days = diff.days; hours = diff.seconds // 3600; mins = (diff.seconds % 3600) // 60
                            if days > 0: age_str = f"{days}d {hours}h"
                            elif hours > 0: age_str = f"{hours}h {mins}m"
                            else: age_str = f"{mins}m"
                    except: age_str = "?"

                    stop="-"; t1="-"; t2="-"; t3="-"
                    if sym in self.oco: 
                        rule = self.oco[sym]
                        stop = f"${rule.get('stop', 0)}"
                        targets = rule.get('targets', [])
                        if targets:
                            if len(targets) > 0: t1 = f"${targets[0]['price']}"
                            if len(targets) > 1: t2 = f"${targets[1]['price']}"
                            if len(targets) > 2: t3 = f"${targets[2]['price']}"
                        else:
                            t1 = f"${rule.get('take', 0)}"

                    pct_pl = (upnl / cost * 100) if cost != 0 else 0.0
                    
                    # Parse Raw Expiry
                    raw_expiry = None
                    if p.get('ExpirationDate'):
                        try:
                            d_obj = datetime.datetime.fromisoformat(p['ExpirationDate'].replace('Z', '+00:00'))
                            raw_expiry = d_obj.strftime('%Y-%m-%d')
                        except: pass

                    self.pos_map[sym] = {
                        'sym':sym, 'desc':f"{nm} ({exp})", 'mkt':_to_float(p.get('Last',0)), 
                        'stk':stk_val, 'dte':dte_val, 'typ':typ, 'qty': q, 'pnl': pct_pl,
                        'mkt_val': mkt_val, 'cost': cost, 'AveragePrice': _to_float(p.get('AveragePrice', 0)),
                        'raw_expiry': raw_expiry,
                        'Delta': p.get('Delta', 0), 'Gamma': p.get('Gamma', 0),
                        'Theta': p.get('Theta', 0), 'Vega': p.get('Vega', 0),
                        'ImpliedVolatility': p.get('ImpliedVolatility', 0)
                    }
                    
                    # Row Update Logic
                    k = sym
                    seen_keys.add(k)
                    
                    # CONTRACT, EXP, QTY, VAL, P/L, AGE, STOP, T1, T2, T3
                    vals = (
                        Text(nm, style="green" if typ=="C" else "red"), 
                        exp, 
                        str(q), 
                        f"{mkt_val/eq*100:.1f}%" if eq != 0 else "0.0%", 
                        Text(f"{pct_pl:+.1f}%", style="green" if upnl>=0 else "red"), 
                        age_str, 
                        stop, t1, t2, t3
                    )
                    
                    if k in tbl.rows:
                        # Smart Update
                        for i in range(10): smart_update(k, i, vals[i])
                    else:
                        tbl.add_row(*vals, key=k)
                        updates_this_cycle += 1
                    

                
                # 3. Clean Obsolete Rows
                # Iterate over keys in table, remove if not in seen_keys
                # Note: modifying list while iterating rows is dangerous for row_key access, 
                # 3. Clean Obsolete Rows
                curr_rows = set(tbl.rows.keys())
                to_remove = []
                for k in curr_rows:
                    if k not in seen_keys:
                        to_remove.append(k)
                        tbl.remove_row(k)
                # DEBUG FLICKER
                if to_remove or (len(seen_keys) > len(curr_rows)):
                     added = seen_keys - curr_rows
                     # self.log_msg(f"FLICKER DEBUG: Added={list(added)} Removed={to_remove}")
                     
                # self.log_msg(f"CYCLE STATS: Updates={updates_this_cycle} EmptyCount={self.empty_payload_count if hasattr(self,'empty_payload_count') else 0}")
                
                # --- ANTIGRAVITY PORTFOLIO DUMP ---
                active_pos = None
                xp = self.query_one(ExecutionPanel)
                selected_sym = xp.pos_sym
                
                if selected_sym and selected_sym in self.pos_map:
                    active_pos = self.pos_map[selected_sym]
                elif self.pos_map:
                    sorted_pos = sorted(self.pos_map.values(), key=lambda x: x.get('mkt_val', 0), reverse=True)
                    active_pos = sorted_pos[0]
                
                # Construct Snapshot
                                
                # [FIX] Compile Ungrouped Positions for Export
                ungrouped_export = []
                for p in raw_positions:
                    sym = p.get('Symbol')
                    if sym in processed_syms: continue
                    q = int(p.get('Quantity', 0))
                    if q == 0: continue
                    
                    # Need to parse type/strike? Or just dump raw? 
                    # nexus_greeks expecting: ticker, qty, type, strike, expiry, raw
                    # But get_live_portfolio (Step 3790) parses raw 'ticker' (symbol).
                    # It just needs 'ticker' (symbol), 'qty', 'type'.
                    
                    ungrouped_export.append({
                        "ticker": sym,
                        "qty": q,
                        "type": p.get("AssetType", "OPTION"),
                        "raw": sym # nexus_greeks uses this
                    })

                portfolio_snapshot = {
                    "script": "trader_dashboard",
                    "timestamp": datetime.datetime.now().isoformat(),
                    "account_metrics": {
                        "exposure": val_agg if val_agg != 0 else sum_val,
                        "unrealized_pnl": pnl_agg if pnl_agg != 0 else sum_pnl,
                        "equity": eq,
                        "exposure_pct": (val_agg/eq*100) if eq!=0 else 0,
                        "pnl_pct": (pnl_agg/eq*100) if eq!=0 else 0
                    },
                    "grouped_positions": grouped_export, # [NEW] Export Spreads
                    "ungrouped_positions": ungrouped_export, # [FIX]
                    "active_trade": {},
                    "risk_profile": {}
                }

                if active_pos:
                    q = float(active_pos['qty'])
                    is_call = active_pos['typ'] == 'CALL'
                    direction = "BULLISH" if (is_call and q>0) or (not is_call and q<0) else "BEARISH"
                    
                    # Risk Profile
                    risk_profile = {"stop_loss_price": 0.0, "profit_target": 0.0, "invalidation_condition": "Manual/None"}
                    
                    lookup_sym = active_pos['sym'].replace(" ", "")
                    rule = self.oco.get(lookup_sym) or self.oco.get(active_pos['sym'])
                    
                    if rule:
                        risk_profile["stop_loss_price"] = rule.get('stop', 0)
                        targets = rule.get('targets', [])
                        if targets:
                            risk_profile["profit_targets"] = [t['price'] for t in targets]
                            risk_profile["profit_target"] = targets[0]['price']
                        else:
                            risk_profile["profit_target"] = rule.get('take', 0)

                    # Avg Price
                    avg_price = _to_float(active_pos.get('AveragePrice', 0))
                    if avg_price == 0 and active_pos['qty'] != 0:
                        avg_price = (active_pos['cost'] / active_pos['qty'] / 100)

                    portfolio_snapshot["active_trade"] = {
                        "ticker": active_pos['sym'], 
                        "qty": float(active_pos['qty']),
                        "type": active_pos['typ'],
                        "strike": active_pos['stk'],
                        "direction": direction,
                        "expiry": active_pos.get('raw_expiry'),
                        "pnl_pct": active_pos.get('pnl', 0.0),
                        "avg_price": avg_price
                    }
                    portfolio_snapshot["risk_profile"] = risk_profile

                asyncio.create_task(async_antigravity_dump("nexus_portfolio.json", portfolio_snapshot))

                final_val = val_agg if val_agg != 0 else sum_val; final_pnl = pnl_agg if pnl_agg != 0 else sum_pnl
                if eq != 0:
                    self.query_one("#m-acct", Metric).update_val("OK","green"); self.query_one("#m-exp", Metric).update_val(f"{final_val/eq*100:.1f}%","#88c0d0"); self.query_one("#m-pl", Metric).update_val(f"{final_pnl/eq*100:.2f}%","#a3be8c" if final_pnl>=0 else "#bf616a")
                else:
                    self.query_one("#m-acct", Metric).update_val("OK","green"); self.query_one("#m-exp", Metric).update_val(f"0.0%","#88c0d0"); self.query_one("#m-pl", Metric).update_val(f"0.00%","#bf616a")
            except Exception as e:
                self.log_msg(f"ACCT LOOP ERR: {e}")
                import traceback
                self.log_msg(traceback.format_exc())
                await asyncio.sleep(2)

    def group_positions(self, positions):
        """
        Groups positions into spreads based on logic from nexus_spreads.py.
        Updated to support PARTIAL SPREADS and LEGGED SPREADS.
        Returns: (grouped_list, grouped_data_export, processed_ids_set)
        NOTE: V3 expects Dictionaries in grouped_display.
        """
        from collections import defaultdict
        import copy
        import re
        import datetime
        
        # 0. Deep Copy positions to allow modification (handling remainders)
        working_positions = copy.deepcopy(positions)
        
        # 1. Map Positions by Symbol for quick lookup
        pos_map = {p.get("Symbol"): p for p in working_positions}
        grouped_display = []
        grouped_data = [] # For JSON export
        processed_syms = set() # Track symbols fully consumed

        # 2. PRIMARY PASS: Group by Timestamp (Creation Time)
        time_groups = defaultdict(list)
        for p in working_positions:
            ts = p.get("Timestamp") or p.get("DateAcquired") or p.get("Created")
            if ts:
                time_groups[ts].append(p)
        
        for ts, group in time_groups.items():
            # Filter out already processed symbols
            active_group = [p for p in group if p.get("Symbol") not in processed_syms]
            
            if len(active_group) == 2:
                p1 = active_group[0]; p2 = active_group[1]
                q1 = float(p1.get("Quantity", 0)); q2 = float(p2.get("Quantity", 0))
                
                # Check for Spread Characteristics:
                if (q1 * q2 < 0):
                    # Partial Match Logic
                    abs_q1 = abs(q1)
                    abs_q2 = abs(q2)
                    common_qty = min(abs_q1, abs_q2)
                    
                    if common_qty > 0:
                        sym1 = p1.get("Symbol"); sym2 = p2.get("Symbol")
                        short_p = p1 if q1 < 0 else p2
                        long_p = p2 if q1 < 0 else p1
                        short_sym = short_p.get("Symbol")
                        long_sym = long_p.get("Symbol")
                        
                        ratio_short = common_qty / abs(float(short_p.get("Quantity", 1)))
                        ratio_long = common_qty / abs(float(long_p.get("Quantity", 1)))
                        
                        pl_short = float(short_p.get("UnrealizedProfitLoss", 0)) * ratio_short
                        pl_long = float(long_p.get("UnrealizedProfitLoss", 0)) * ratio_long
                        val_short = float(short_p.get("MarketValue", 0)) * ratio_short
                        val_long = float(long_p.get("MarketValue", 0)) * ratio_long
                        
                        pl_net = pl_short + pl_long
                        val_net = val_short + val_long
                        
                        cost_basis = val_net - pl_net
                        pl_pct_str = "0.0%"
                        pl_pct = 0.0
                        if cost_basis != 0:
                            pl_pct = (pl_net / abs(cost_basis)) * 100
                            pl_pct_str = f"{pl_pct:+.1f}%"
                            
                        # Format Label
                        label = "SPREAD"
                        try:
                            s_tok = short_sym.strip().split()[-1]
                            l_tok = long_sym.strip().split()[-1]
                            def parse_s(tok):
                                if 'C' in tok: idx=tok.rfind('C'); typ='C'
                                elif 'P' in tok: idx=tok.rfind('P'); typ='P'
                                else: return None, None
                                return typ, float(tok[idx+1:])
                            typ_s, k_s = parse_s(s_tok)
                            typ_l, k_l = parse_s(l_tok)
                            if k_s > 10000: k_s /= 1000
                            if k_l > 10000: k_l /= 1000
                            label_prefix = "?"
                            if typ_s == 'C': 
                                if k_l < k_s: label_prefix = "DEBIT CALL"
                                else: label_prefix = "CREDIT CALL"
                            elif typ_s == 'P':
                                if k_l < k_s: label_prefix = "CREDIT PUT"
                                else: label_prefix = "DEBIT PUT"
                            label = f"{label_prefix} ({k_s:g}/{k_l:g})"
                        except: pass

                        exp_str = "-"
                        try:
                            ts_raw = short_p.get('ExpirationDate')
                            if ts_raw:
                                d = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                now = datetime.datetime.now(d.tzinfo); days = (d.date() - now.date()).days
                                exp_str = f"{d.strftime('%b %d')} ({days}d)"
                        except: pass

                        age_str = "?"
                        try:
                            ts_raw = short_p.get("Timestamp") or short_p.get("DateAcquired") or short_p.get("Created")
                            if ts_raw:
                                if "T" in ts_raw: dt = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                else: dt = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                                now = datetime.datetime.now(dt.tzinfo)
                                delta = now - dt
                                if delta.days > 0: age_str = f"{delta.days}d"
                                else: age_str = f"{delta.seconds // 3600}h"
                        except: pass

                        grouped_display.append({
                            "label": label,
                            "exp": exp_str,
                            "qty": str(int(common_qty)),
                            "pl": pl_pct_str,
                            "val": f"${val_net:.2f}",
                            "key": f"AUTO|{short_sym}|{long_sym}",
                            "raw_pl": pl_net,
                            "raw_val": val_net,
                            "pl_pct": pl_pct,
                            "age": age_str
                        })
                        
                        new_q1 = abs_q1 - common_qty
                        new_q2 = abs_q2 - common_qty
                        p1['Quantity'] = new_q1 * (-1 if q1 < 0 else 1)
                        p2['Quantity'] = new_q2 * (-1 if q2 < 0 else 1)
                        
                        if new_q1 <= 0.001: processed_syms.add(sym1)
                        else: 
                            if sym1 in processed_syms: processed_syms.remove(sym1)
                        if new_q2 <= 0.001: processed_syms.add(sym2)
                        else:
                            if sym2 in processed_syms: processed_syms.remove(sym2)

        # 3. SECONDARY PASS: Loose Grouping
        orthan_map = defaultdict(list)
        for p in working_positions:
             sym = p.get("Symbol")
             if sym in processed_syms: continue
             if abs(float(p.get("Quantity",0))) < 0.001: continue
             root = sym.split()[0]
             ts_exp = p.get("ExpirationDate", "").split("T")[0]
             if root and ts_exp:
                 orthan_map[(root, ts_exp)].append(p)
                 
        for k, group in orthan_map.items():
             shorts = [p for p in group if float(p.get("Quantity",0)) < 0]
             longs = [p for p in group if float(p.get("Quantity",0)) > 0]
             
             # [DEBUG] Trace Secondary Grouping
             # self.log_msg(f"DEBUG: Secondary Key {k} has {len(shorts)} shorts, {len(longs)} longs.")
             
             shorts.sort(key=lambda x: abs(float(x.get("Quantity",0))), reverse=True)
             longs.sort(key=lambda x: abs(float(x.get("Quantity",0))), reverse=True)
             
             while shorts and longs:
                 p1 = shorts.pop(0); p2 = longs.pop(0)
                 q1 = float(p1.get("Quantity", 0)); q2 = float(p2.get("Quantity", 0))
                 common_qty = min(abs(q1), abs(q2))
                 
                 if common_qty > 0:
                        sym1 = p1.get("Symbol"); sym2 = p2.get("Symbol")
                        short_p = p1; long_p = p2
                        short_sym = short_p.get("Symbol"); long_sym = long_p.get("Symbol")

                        ratio_short = common_qty / abs(float(short_p.get("Quantity", 1)))
                        ratio_long = common_qty / abs(float(long_p.get("Quantity", 1)))
                        
                        pl_short = float(short_p.get("UnrealizedProfitLoss", 0)) * ratio_short
                        pl_long = float(long_p.get("UnrealizedProfitLoss", 0)) * ratio_long
                        val_short = float(short_p.get("MarketValue", 0)) * ratio_short
                        val_long = float(long_p.get("MarketValue", 0)) * ratio_long
                        
                        pl_net = pl_short + pl_long
                        val_net = val_short + val_long
                        
                        cost_basis = val_net - pl_net
                        pl_pct_str = "0.0%"
                        if cost_basis != 0:
                            pl_pct = (pl_net / abs(cost_basis)) * 100
                            pl_pct_str = f"{pl_pct:+.1f}%"
                        else: pl_pct=0.0

                        label = "SPREAD (LEGGED)"
                        try:
                            s_tok = short_sym.strip().split()[-1]
                            l_tok = long_sym.strip().split()[-1]
                            def parse_s(tok):
                                if 'C' in tok: idx=tok.rfind('C'); typ='C'
                                elif 'P' in tok: idx=tok.rfind('P'); typ='P'
                                else: return None, None
                                return typ, float(tok[idx+1:])
                            typ_s, k_s = parse_s(s_tok)
                            typ_l, k_l = parse_s(l_tok)
                            if k_s > 10000: k_s /= 1000
                            if k_l > 10000: k_l /= 1000
                            label_prefix = "?"
                            if typ_s == 'C': 
                                if k_l < k_s: label_prefix = "DEBIT CALL"
                                else: label_prefix = "CREDIT CALL"
                            elif typ_s == 'P':
                                if k_l < k_s: label_prefix = "CREDIT PUT"
                                else: label_prefix = "DEBIT PUT"
                            label = f"{label_prefix} ({k_s:g}/{k_l:g})"
                        except: pass

                        exp_str = "-"
                        try:
                            ts_raw = short_p.get('ExpirationDate')
                            if ts_raw:
                                d = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                now = datetime.datetime.now(d.tzinfo); days = (d.date() - now.date()).days
                                exp_str = f"{d.strftime('%b %d')} ({days}d)"
                        except: pass

                        age_str = "?"
                        try:
                            ts_raw = short_p.get("Timestamp") or short_p.get("DateAcquired") or short_p.get("Created")
                            if ts_raw:
                                if "T" in ts_raw: dt = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                                else: dt = datetime.datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S")
                                now = datetime.datetime.now(dt.tzinfo)
                                delta = now - dt
                                if delta.days > 0: age_str = f"{delta.days}d"
                                else: age_str = f"{delta.seconds // 3600}h"
                        except: pass

                        grouped_display.append({
                            "label": label,
                            "exp": exp_str,
                            "qty": str(int(common_qty)),
                            "pl": pl_pct_str,
                            "val": f"${val_net:.2f}",
                            "key": f"AUTO|{short_sym}|{long_sym}",
                            "raw_pl": pl_net,
                            "raw_val": val_net,
                            "pl_pct": pl_pct,
                            "age": age_str
                        })
                        
                        grouped_data.append({
                            "type": "VERTICAL_SPREAD",
                            "short_leg": short_sym,
                            "long_leg": long_sym,
                            "qty": str(int(common_qty)),
                            "net_pl": pl_net,
                            "net_val": val_net,
                            "pl_pct": pl_pct,
                            "timestamp": "" 
                        })
                        
                        new_q1 = abs(q1) - common_qty
                        new_q2 = abs(q2) - common_qty
                        p1['Quantity'] = new_q1 * (-1 if q1 < 0 else 1); p2['Quantity'] = new_q2 * (-1 if q2 < 0 else 1)
                        
                        if new_q1 > 0: shorts.insert(0, p1)
                        if new_q2 > 0: longs.insert(0, p2)
                        
                        if new_q1 <= 0.001: processed_syms.add(sym1)
                        else:
                            if sym1 in processed_syms: processed_syms.remove(sym1)
                        if new_q2 <= 0.001: processed_syms.add(sym2)
                        else:
                            if sym2 in processed_syms: processed_syms.remove(sym2)

        return grouped_display, grouped_data, processed_syms

    async def poll_account(self):
        while True:
            try:
                if is_sleep_mode():
                    await asyncio.sleep(60)
                    continue

                # Use main context, create fresh socket
                sock = self.zmq_ctx.socket(zmq.REQ)
                sock.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_ACCOUNT}") # Use ACCOUNT port for TS Manager direct query? 
                # Wait, TS Manager publishes on PUB. 
                # But we want to REQUEST data to be sure? 
                # Actually ts_nexus.py has a poll_account loop that PUBLISHES.
                # But we also have a REQ/REP for execution.
                # Let's stick to the existing pattern if it works.
                # The existing code was using self.sub_sock? No, it was missing from the snippet.
                # Ah, the snippet I replaced was 'async def poll_account(self): ...'
                # It seems I need to implement the polling logic properly.
                # The original code was likely using REQ to 'GET_ACCOUNT' or similar if it exists,
                # OR it was just a loop that updates the UI from a local cache populated by SUB?
                # Let's look at how it was implemented.
                # It seems I am replacing lines 850-905 which was INSIDE poll_account?
                # No, wait. The previous `view_file` showed `poll_account` was NOT in the snippet.
                # The snippet 850-905 was inside `update_account_table` or similar?
                # Let me check the file content again.
                # Lines 850-905 seem to be inside `update_account_ui` or `on_account_data`.
                # Wait, I need to be careful.
                # The previous view showed `async def sub_sel(self):` at 907.
                # The lines 850-905 were inside a method that calculates portfolio snapshot.
                # I need to find the method signature.
                pass
            except: pass
            await asyncio.sleep(1)
            
    # [CORRECTION] I need to replace the `update_positions_table` or similar method.
    # Let me re-read the file to find the correct method to replace.
    # The snippet 850-905 was calculating `portfolio_snapshot`.
    # It was likely inside `update_account_info(self, data)`.


    async def sub_sel(self):
        s=self.zmq_ctx.socket(zmq.SUB)
        for p in LISTEN_PORTS: s.connect(f"tcp://{LOCAL_IP}:{p}")
        s.subscribe(b"SELECT"); s.subscribe(b"SELECT_SWEEP")
        while True:
            try:
                msg=await s.recv_multipart()
                try: d = json.loads(msg[1])
                except: d = json.loads(msg[1].decode('utf-8'))
                if 'symbol' in d: self.contract_map[d['symbol']] = d; self.load_contract(d)
            except: await asyncio.sleep(1)

    def load_contract(self, d):
        xp = self.query_one(ExecutionPanel)
        xp.sym=d.get('symbol'); xp.stk=d.get('stk'); xp.dte=d.get('dte'); xp.typ=d.get('type'); xp.price=d.get('mkt',0)
        xp.watch_sym(xp.sym); xp.watch_price(xp.price)
        xp.occ_sym = d.get('occ_sym') # Store OCC Symbol for Live Updates
        xp.vol = int(d.get('vol', 0)) # Initialize Volume
        xp.query_one("#inp-limit", Input).value = f"{xp.price:.2f}"
        self.pub.send_multipart([b"SUB", xp.sym.encode()])
        self.query_one("#tbl-con", DataTable).clear()
        
        # Ensure 'd' has all fields expected by fmt_row
        # Hunter sends: symbol, stk, type, exp, mkt, dte, vol, oi, delta, gamma, theta, vega, iv
        
        # Map missing fields & Calculate Derived Stats
        d['prem'] = d.get('mkt', 0) * 100 * d.get('vol', 0) # Estimate premium if missing
        d['voi_ratio'] = d.get('vol', 0) / d.get('oi', 1) if d.get('oi', 0) > 0 else 0.0
        d['pc_ratio_vol'] = 0 # Not in Hunter payload
        d['pc_ratio_oi'] = 0 # Not in Hunter payload
        d['theo'] = d.get('mkt', 0) # Use MKT as Theo if missing
        d['edge'] = 0 # Not in Hunter payload
        d['conf'] = "HUNTER"
        
        # Calculate Break Even
        stk = d.get('stk', 0); mkt = d.get('mkt', 0); typ = d.get('type', 'CALL')
        d['be'] = stk + mkt if typ == 'CALL' else stk - mkt
        
        # Win % (Delta Proxy)
        delta = abs(d.get('delta', 0))
        d['win'] = f"{delta*100:.0f}%"

        self.query_one("#tbl-con", DataTable).add_row(*fmt_row(d), key=d.get('symbol'))
    async def sub_ts_stream(self):
        """
        Listens to Direct TradeStation Option Stream (Control-driven).
        Updates 'Mkt' price instantly when user selects a contract.
        """
        ctx = zmq.asyncio.Context()
        sock = ctx.socket(zmq.SUB)
        try:
            sock.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_OPTION_TICK}")
            sock.subscribe(b"OPTION_TICK")
            self.log_msg("connected to TS Option Stream (5569)")
            
            while True:
                try:
                    topic, msg = await sock.recv_multipart()
                    d = json.loads(msg.decode('utf-8'))
                    
                    # Check for Active Contract Match
                    xp = self.query_one(ExecutionPanel)
                    
                    # Match by Symbol (TS Format: SPY 250116C600)
                    stream_sym = d.get('Symbol')
                    
                    # Robust Matching: Check if streamed symbol matches dashboard's current focus
                    # Dashboard uses `xp.sym` (which might be "SPY 250116C600" or OCC)
                    # `load_contract` sets `xp.sym` to the TS format usually.
                    
                    if stream_sym and xp.sym and (stream_sym == xp.sym or stream_sym == xp.occ_sym):
                        # Extract Price (Last > Mid > Bid/Ask)
                        new_price = 0.0
                        if "Last" in d: new_price = float(d['Last'])
                        elif "Bid" in d and "Ask" in d:
                             new_price = (float(d['Bid']) + float(d['Ask'])) / 2.0
                        
                        if new_price > 0:
                            # Update UI
                            xp.price = new_price
                            xp.watch_price(xp.price)
                            
                            # Visual Feedback of liveness
                            # Maybe flash the label color? For now just update text.
                            
                            # Also update table if present
                            try:
                                self.query_one("#tbl-con", DataTable).update_cell(xp.sym, "MKT($)", f"{new_price:.2f}")
                            except: pass
                            
                except Exception as e:
                    # self.log_msg(f"Stream Err: {e}")
                    await asyncio.sleep(0.1)
        except Exception as e:
            self.log_msg(f"TS Stream Bind Err: {e}")
    async def sub_option_tick(self):
        ctx = zmq.asyncio.Context()
        # Connect to UW Nexus (Port 9999)
        sock = ctx.socket(zmq.SUB)
        sock.connect(f"tcp://{LOCAL_IP}:9999")
        sock.subscribe(b"option_trades")
        
        while True:
            try:
                topic, msg = await sock.recv_multipart()
                d = json.loads(msg.decode('utf-8'))
                
                # Check for Active Contract Match
                xp = self.query_one(ExecutionPanel)
                if xp.occ_sym and d.get('option_symbol') == xp.occ_sym:
                    # Update Price
                    new_price = float(d.get('price', 0))
                    if new_price > 0:
                        xp.price = new_price
                        xp.watch_price(xp.price)
                        
                        # Update Volume
                        trade_size = int(d.get('size', 0))
                        if trade_size > 0:
                            xp.vol += trade_size
                        
                        # Update Table MKT & VOL Column
                        try:
                            dt = self.query_one("#tbl-con", DataTable)
                            dt.update_cell(xp.sym, "MKT($)", f"{new_price:.2f}")
                            dt.update_cell(xp.sym, "VOL", f"{xp.vol}")
                        except: pass
            except Exception as e:
                # self.log_msg(f"Tick Error: {e}")
                await asyncio.sleep(0.1)

    async def sub_logs(self):
        ctx = zmq.asyncio.Context()
        sock = ctx.socket(zmq.SUB); sock.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_LOGS}"); sock.subscribe(b"LOG")
        log_widget = self.query_one("#event_log", Log)
        while True:
            try:
                _, msg_bytes = await sock.recv_multipart()
                msg = msg_bytes.decode('utf-8')
                log_widget.write(Text.from_markup(f"[dim]NEXUS:[/dim] {msg}"))
            except: await asyncio.sleep(1)

    async def send_order(self, cmd, qty, sym, price=None, limit_price=None, stop=None, take=None, targets=None, type="C", reason=None, dte=0, side="SELL"):
        if limit_price is not None: price = limit_price
        payload = {"cmd": cmd, "symbol": sym, "qty": qty, "price": price, "stop": stop, "take": take, "targets": targets, "type": type, "reason": reason, "dte": dte, "side": side}
        
        # Handle Partial Exit Mapping
        if cmd == "EXIT_PARTIAL":
            payload["cmd"] = "SELL" # Map to standard SELL
            if not reason: reason = "EXIT_PARTIAL"
            
        if reason: payload["reason"] = reason
        if dte is not None: payload["dte"] = dte
        
        # Risk Params
        if stop is not None and stop > 0: payload["stop"] = str(stop)
        
        # [FIX] limit_price is not passed as argument, but 'price' is.
        # The original code used 'limit_price' variable which is undefined in this scope!
        # It should use 'price'.
        if price: 
            payload["price"] = str(price)
            payload["duration"] = "GTC" # [FIX] Default to Good Till Cancelled
            payload["type"] = "LIMIT"
        else:
            payload["duration"] = "DAY" # Market orders usually DAY
            payload["type"] = "MARKET"
            
        if take is not None and take > 0: payload["take"] = str(take)
        if targets: payload["targets"] = targets
            
        # Add Risk Data for ARM command
        if cmd == "ARM":
            payload["stop"] = stop
            payload["take"] = take
            payload["type"] = type # 'C' or 'P' (Confusing naming conflict in payload, but handled)
        
        try:
            await self.ex.send_json(payload)
            if await self.ex.poll(5000): 
                resp = await self.ex.recv_json()
                if resp.get("status") == "ok": 
                    self.log_msg(f"CONFIRMED: {resp.get('msg', 'SENT')}")
                else: 
                    self.log_msg(f"REJECT: {resp.get('msg')}")
            else:
                self.log_msg("TIMEOUT! Resetting Socket...")
                self.ex.close(); self.ex = self.zmq_ctx.socket(zmq.REQ); self.ex.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
        except Exception as e: self.log_msg(f"EXEC FAIL: {e}")

    async def fetch_open_orders(self):
        """Periodically fetch open orders from backend."""
        while True:
            try:
                if is_sleep_mode():
                    await asyncio.sleep(60)
                    continue

                # Use main context, create fresh socket
                sock = self.zmq_ctx.socket(zmq.REQ)
                sock.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
                
                await sock.send_json({"cmd": "GET_OPEN_ORDERS"})
                if await sock.poll(2000):
                    resp = await sock.recv_json()
                    if resp.get("status") == "ok":
                        orders = resp.get("orders", [])
                        # [DEBUG] Log fetched count
                        if len(orders) > 0: self.log_msg(f"DEBUG: Fetched {len(orders)} open orders")
                        self.update_orders_table(orders)
                    else:
                        # [DEBUG] Log backend errors
                        self.log_msg(f"DEBUG: Fetch Error: {resp.get('msg')}")
                
                sock.close()
            except Exception as e: 
                self.log_msg(f"DEBUG: Fetch Loop Error: {e}")
                import traceback
                traceback.print_exc()
            await asyncio.sleep(3)

    def update_orders_table(self, orders):
        dt = self.query_one("#tbl-ord", DataTable)
        
        # 1. Map existing rows
        existing_ids = {str(k.value) for k in dt.rows.keys()}
        # self.log_msg(f"DEBUG: Table has {len(existing_ids)} rows. IDs: {list(existing_ids)}")
        
        new_orders_map = {str(o.get("OrderID")): o for o in orders}
        new_ids = set(new_orders_map.keys())
        
        # 2. Remove stale
        for oid in existing_ids - new_ids:
            dt.remove_row(oid)
            
        # 3. Add / Update
        # 3. Add / Update
        for oid in new_ids:
            if oid in self.dismissed_orders: continue
            o = new_orders_map[oid]
            # [DEBUG] Log keys for first order to check structure
            if oid == list(new_ids)[0]:
                self.log_msg(f"DEBUG: Order Keys: {list(o.keys())}")

            sym = o.get("Symbol", "UNK")
            # TradeStation might return 'Legs' instead of TradeAction at top level
            side = o.get("TradeAction")
            if not side:
                # Try to find side in Legs if present
                legs = o.get("Legs", [])
                if legs and len(legs) > 0:
                    side = legs[0].get("BuyOrSell", "UNK")
                else:
                    side = "UNK"
            
            qty = str(o.get("Quantity", 0))
            typ = o.get("OrderType", "UNK")
            prc = str(o.get("LimitPrice", "MKT"))
            stat = o.get("Status", "UNK")
            
            # Safeguard color logic
            color = "white"
            if side:
                if "Buy" in side or "BUY" in side: color = "green"
                elif "Sell" in side or "SELL" in side: color = "red"
            side_styled = Text(str(side), style=color)
            
            if oid not in existing_ids:
                # [DEBUG] Log addition
                self.log_msg(f"DEBUG: Adding Order {oid} to table")
                dt.add_row(oid, sym, side_styled, qty, typ, prc, stat, key=oid)
                self.log_msg(f"DEBUG: Successfully added Order {oid}")
            else:
                # Update cells if needed? Textual DataTable doesn't support easy cell update without clearing row.
                # But status might change.
                # For now, if status changes, we could re-add.
                # Let's just leave it unless we want to be fancy.
                pass

    @on(DataTable.RowSelected, "#tbl-ord")
    def on_ord_click(self, e):
        # Show Cancel Button
        self.query_one("#btn-cancel").styles.display = "block"
        self.selected_order_id = e.row_key.value

    @on(Button.Pressed, "#btn-cancel")
    def cancel_selected_order(self):
        if hasattr(self, "selected_order_id") and self.selected_order_id:
            self.app.run_worker(self.send_cancel(self.selected_order_id))
            self.query_one("#btn-cancel").styles.display = "none"

    async def send_cancel(self, oid):
        try:
            # Use main exec socket
            await self.ex.send_json({"cmd": "CANCEL_ORDER", "order_id": oid})
            resp = await self.ex.recv_json()
            if resp.get("status") == "ok":
                self.log_msg(f"CANCEL SENT: {oid}")
            else:
                self.log_msg(f"CANCEL FAIL: {resp.get('msg')}")
        except Exception as e: self.log_msg(f"CANCEL ERR: {e}")

if __name__ == "__main__": TraderDashboardV2().run()