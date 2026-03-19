import sys, os, asyncio, json, datetime
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Button, Static, Input, Label, Log
from textual.containers import Container, Horizontal, Vertical, Grid
from textual.reactive import reactive
from textual import work, on
import zmq
import zmq.asyncio

# CONFIG
ZMQ_PORT_MARKET = 5555
ZMQ_PORT_EXEC = 5567
TARGET_SYMBOL = "MESM26"
FUTURES_ACCOUNT_ID = "210VGM01"
DELTA_MULTIPLIER = 50.0 # Micro E-Mini Multiplier (SPY-Equivalent Delta)
LOCAL_IP = "127.0.0.1"

class MetricVar(Static):
    """Display a label and a value."""
    def __init__(self, label, id=None):
        super().__init__(id=id)
        self.label = label
        self.value = "---"
    
    def compose(self):
        yield Label(self.label, classes="metric-label")
        yield Label(self.value, id=f"{self.id}-val", classes="metric-value")
    
    def update_val(self, new_val, color="white"):
        lbl = self.query_one(f"#{self.id}-val", Label)
        lbl.update(str(new_val))
        lbl.styles.color = color

class NexusHedgeApp(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #1e1e1e;
    }
    Header {
        dock: top;
        background: #004400;
        color: white;
    }
    #header-container {
        text-align: center;
        color: green;
        text-style: bold;
        margin: 1;
        height: 3;
    }
    .metric-container {
        layout: horizontal;
        height: 10;
        margin: 1;
    }
    MetricVar {
        width: 1fr;
        content-align: center middle;
        background: #2e2e2e;
        margin: 1;
        border: solid #444;
    }
    .metric-label {
        width: 100%;
        text-align: center;
        color: #888;
    }
    .metric-value {
        width: 100%;
        text-align: center;
        text-style: bold;
    }
    .controls {
        layout: horizontal;
        height: 5;
        align: center middle;
        margin-top: 2;
    }
    .qty-lbl {
        margin-top: 1;
    }
    Button {
        margin: 1 2;
        width: 20;
    }
    Input {
        width: 10;
        text-align: center;
    }
    Log {
        height: 1fr;
        border: solid green;
        margin: 1;
    }
    """

    price = reactive(0.0)
    qty = reactive(1)
    pnl_pct = reactive(0.0)
    hedged_delta = reactive(0.0)
    
    # NEW REACTIVES
    port_delta = reactive(0.0)
    port_gamma = reactive(0.0)
    
    # State tracking
    qty_held = 0
    pnl_val = 0.0
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Container(
            Label(f"FUTURES HEDGE | {TARGET_SYMBOL} | ACCT: {FUTURES_ACCOUNT_ID}", id="title"),
            id="header-container"
        )
        
        with Horizontal(classes="metric-container"):
            yield MetricVar("MKT PRICE", id="m-price")
            yield MetricVar("PNL %", id="m-pnl")
            yield MetricVar("HEDGE δ", id="m-delta")
            yield MetricVar("NET QTY", id="m-qty")
            
        with Horizontal(classes="metric-container"):
            yield MetricVar("PORTFOLIO δ", id="m-p-delta")
            yield MetricVar("PORTFOLIO γ", id="m-p-gamma")

        with Horizontal(classes="controls"):
            yield Label("QTY:", classes="qty-lbl")
            yield Input(value="1", id="inp-qty", type="integer")
            yield Button("BUY MKT", id="btn-buy", variant="success")
            yield Button("SELL MKT", id="btn-sell", variant="error")
        
        yield Log(id="log")
        yield Footer()

    def on_mount(self):
        self.ctx = zmq.asyncio.Context()
        self.log_msg("Initializing Nexus Hedge...")
        self.run_worker(self.sub_market())
        self.run_worker(self.poll_positions())
        self.run_worker(self.poll_market_state()) # NEW
        self.run_worker(self.export_hedge_state()) # NEW

    def log_msg(self, msg):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        try: self.query_one(Log).write_line(f"[{now}] {msg}")
        except: pass
        
        with open("nexus_hedge_debug.log", "a") as f:
            f.write(f"[{now}] {msg}\n")

    # --- NEW METHODS ---
    async def poll_market_state(self):
        """Read Portfolio Greeks from market_state.json"""
        while True:
            try:
                if os.path.exists("market_state.json"):
                    # Non-blocking read
                    data = await asyncio.to_thread(self.read_json, "market_state.json")
                    if data:
                        # Extract Greeks
                        active_pos = data.get("active_position", {})
                        greeks = active_pos.get("greeks", {})
                        
                        self.port_delta = float(greeks.get("delta", 0))
                        self.port_gamma = float(greeks.get("gamma", 0))
                        
                        # Update UI
                        self.query_one("#m-p-delta", MetricVar).update_val(f"{self.port_delta:.0f}", color="yellow")
                        self.query_one("#m-p-gamma", MetricVar).update_val(f"{self.port_gamma:.0f}", color="yellow")
                        
                        # Update Net Metrics
                        self.calc_net_greeks()
            except Exception as e:
                pass
            await asyncio.sleep(5)

    def read_json(self, path):
        try:
            with open(path, 'r') as f: return json.load(f)
        except: return None

    async def export_hedge_state(self):
        """Write current hedge state for Auditor."""
        while True:
            try:
                state = {
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                    "symbol": TARGET_SYMBOL,
                    "qty": self.qty_held, 
                    "hedged_delta": self.hedged_delta,
                    "pnl": self.pnl_val
                }
                # Atomic Write output
                await asyncio.to_thread(self.atomic_write, "hedge_state.json", state)
            except Exception as e:
                self.log_msg(f"Export Err: {e}")
            await asyncio.sleep(5)
            
    def atomic_write(self, filename, data):
        temp = f"{filename}.tmp"
        with open(temp, 'w') as f: json.dump(data, f)
        os.replace(temp, filename)

    def calc_net_greeks(self):
        pass # Placeholder for net calculation if needed

    # --- RESTORED METHODS ---
    async def sub_market(self):
        """Subscribe to MESM26 market data."""
        sock = self.ctx.socket(zmq.SUB)
        sock.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_MARKET}")
        sock.subscribe(TARGET_SYMBOL.encode())
        self.log_msg(f"Connected to Market Stream ({ZMQ_PORT_MARKET}) for {TARGET_SYMBOL}")
        
        while True:
            try:
                topic, msg = await sock.recv_multipart()
                d = json.loads(msg.decode('utf-8'))
                
                if "Last" in d:
                    self.price = float(d['Last'])
                    self.query_one("#m-price", MetricVar).update_val(f"{self.price:.2f}")
            except asyncio.CancelledError: break
            except Exception as e:
                pass

    async def poll_positions(self):
        """Periodically fetch positions for Futures Account to calc PNL/Delta."""
        req = self.ctx.socket(zmq.DEALER)
        # Unique Identity to prevent ghost replies
        ident = f"HEDGE_POS_{datetime.datetime.now().timestamp()}".encode()
        req.setsockopt(zmq.IDENTITY, ident)
        req.setsockopt(zmq.RCVHWM, 0)
        req.setsockopt(zmq.SNDHWM, 0)
        self.log_msg(f"Socket Identity: {ident}")
        req.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
        
        while True:
            try:
                # REQUEST: [Empty][JSON]
                payload = json.dumps({"cmd": "GET_POSITIONS", "account_id": FUTURES_ACCOUNT_ID}).encode()
                await req.send_multipart([b'', payload])
                
                # Segmented Polling (10s total, check every 100ms)
                resp = None
                # self.log_msg(f"DEBUG: Sending Req to {LOCAL_IP}...")
                for i in range(100):
                    if await req.poll(100):
                        frames = await req.recv_multipart()
                        if len(frames) >= 2:
                            try:
                                resp = json.loads(frames[1].decode())
                                break
                            except Exception as e:
                                self.log_msg(f"JSON Parse Err: {e}")
                
                if resp:
                    if resp.get("status") == "ok":
                        positions = resp.get("positions", [])
                        self.calc_metrics(positions)
                    else:
                        self.log_msg(f"Pos Error: {resp.get('msg')}")
                else:
                    self.log_msg("Pos Fetch Timeout - Reconnecting...")
                    req.close()
                    req = self.ctx.socket(zmq.DEALER)
                    ident = f"HEDGE_POS_{datetime.datetime.now().timestamp()}".encode()
                    req.setsockopt(zmq.IDENTITY, ident)
                    req.setsockopt(zmq.RCVHWM, 0)
                    req.setsockopt(zmq.SNDHWM, 0)
                    self.log_msg(f"Reconnect ID: {ident}")
                    req.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
                
            except asyncio.CancelledError: break
            except Exception as e:
                self.log_msg(f"Poll Err: {e}")
            
            await asyncio.sleep(2) # Poll every 2s

    def calc_metrics(self, positions):
        """Calculate PNL % and Delta."""
        total_qty = 0
        total_pnl = 0.0
        total_cost = 0.0
        
        for p in positions:
            sym = p.get("Symbol", "")
            if TARGET_SYMBOL in sym: # MESM26 should match MESM26
                q = int(p.get("Quantity", 0))
                pnl = float(p.get("UnrealizedProfitLoss", 0))
                # For Futures, Margin or Cost logic. Using what we have.
                cost = float(p.get("TotalCost", 0)) 
                
                total_qty += q
                total_pnl += pnl
                total_cost += cost

        # Update State
        self.qty_held = total_qty 
        self.pnl_val = total_pnl 
        
        self.hedged_delta = total_qty * DELTA_MULTIPLIER
        self.query_one("#m-delta", MetricVar).update_val(f"{self.hedged_delta:.0f}", color="cyan")
        self.query_one("#m-qty", MetricVar).update_val(str(total_qty))
        
        # PNL %
        pnl_pct = 0.0
        if total_cost != 0:
            pnl_pct = (total_pnl / abs(total_cost)) * 100
        
        c = "green" if total_pnl >= 0 else "red"
        self.query_one("#m-pnl", MetricVar).update_val(f"{pnl_pct:.2f}%", color=c)

    async def send_order(self, side, qty):
        """Send Execution Command with Account override."""
        self.log_msg(f"Sending {side} {qty} {TARGET_SYMBOL}...")
        req = self.ctx.socket(zmq.DEALER)
        req.identity = f"HEDGE_ORD_{datetime.datetime.now().timestamp()}".encode()
        req.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
        
        payload = {
            "cmd": side, # BUY or SELL
            "symbol": TARGET_SYMBOL,
            "qty": qty,
            "type": "MARKET",
            "account_id": FUTURES_ACCOUNT_ID
        }
        
        try:
            await req.send_multipart([b'', json.dumps(payload).encode()])
            if await req.poll(5000):
                frames = await req.recv_multipart()
                if len(frames) >= 2:
                    resp = json.loads(frames[1].decode())
                    if resp.get("status") == "ok":
                        self.log_msg(f"✅ EXECUTED: {resp.get('id', 'OK')}")
                    else:
                        self.log_msg(f"❌ REJECTED: {resp.get('msg')}")
            else:
                self.log_msg("❌ TIMEOUT")
        except Exception as e:
            self.log_msg(f"❌ EXEC ERR: {e}")
        finally:
            req.close()

    @on(Button.Pressed, "#btn-buy")
    def action_buy(self):
        q = int(self.query_one("#inp-qty", Input).value)
        self.run_worker(self.send_order("BUY", q))

    @on(Button.Pressed, "#btn-sell")
    def action_sell(self):
        q = int(self.query_one("#inp-qty", Input).value)
        self.run_worker(self.send_order("SELL", q))

if __name__ == "__main__":
    try:
        app = NexusHedgeApp()
        app.run()
    except Exception as e:
        with open("hedge_crash.log", "w") as f: f.write(str(e))
