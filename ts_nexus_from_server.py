
import asyncio
import datetime
import importlib
import json
import logging
import os
import signal
import ssl
import sys
import threading
import time
import traceback
import aiohttp
import zmq
import zmq.asyncio
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, Log
from textual.containers import Grid, Vertical, Horizontal
from textual import on
from rich.text import Text

# --- CONFIGURATION ---
# --- CONFIGURATION ---
from nexus_config import (
    TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID, 
    DISCORD_WEBHOOK_URL, LIVE_TRADING
)

# Derived / Default Constants
TS_REFRESH_TOKEN = None # Not present in config, defaulting to None (Auth needs handling)
DRY_RUN_EXEC = not LIVE_TRADING # Inverse logic from config

# --- CONSTANTS ---
ZMQ_PORT_EXEC = 5556
ZMQ_PORT_DATA = 5557
ZMQ_PORT_CONTROL = 5558
ALL_SYMBOLS = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "MSFT", "AMZN", "GOOGL", "AMD"]
BAR_SYMBOL = "SPY"
HEADLESS_MODE = "--headless" in sys.argv

# --- UTILS ---
def antigravity_dump(filename, data):
    try:
        with open(filename, 'w') as f: json.dump(data, f, indent=4)
    except: pass

def is_sleep_mode():
    now = datetime.datetime.now().time()
    # M-F 9:30 - 16:00 ET (Approx)
    # Simple check: If before 9:00 or after 16:15, sleep
    # Adjust for local time vs server time needed? Assuming Server is usually UTC or ET.
    # Let's assume Safe Mode: Always Active for now unless critical.
    # User requested fix: "return False" in nexus_config.py
    # But here we check logic.
    return False

# --- TRADESTATION MANAGER (Lazy Load) ---
class TSManagerWrapper:
    def __init__(self):
        self.access_token = None
        self.BASE_URL = "https://api.tradestation.com/v3" 
        
    def refresh_token(self):
        # Placeholder for actual TS Oauth flow
        pass
        
    def place_order(self, account_id, order_payload):
        # Placeholder
        pass
        
    def get_positions(self):
        return []
    
    def get_account_balances(self):
        return []

# Use local library if available
try:
    from tradestation_explorer import TradeStationManager
except:
    TradeStationManager = TSManagerWrapper

# --- CORE ENGINE ---
class NexusEngine:
    def __init__(self):
        self.zmq_ctx = zmq.asyncio.Context()
        self.exec_sock = self.zmq_ctx.socket(zmq.REP); self.exec_sock.bind(f"tcp://*:{ZMQ_PORT_EXEC}")
        self.account_sock = self.zmq_ctx.socket(zmq.PUB); self.account_sock.bind(f"tcp://*:{ZMQ_PORT_DATA}")
        self.bar_sock = self.zmq_ctx.socket(zmq.PUB); self.bar_sock.bind(f"tcp://*:{ZMQ_PORT_DATA + 1}")
        self.option_tick_sock = self.zmq_ctx.socket(zmq.PUB); self.option_tick_sock.bind(f"tcp://*:{ZMQ_PORT_DATA + 2}")
        
        self.running = True
        self.TS = None
        self.positions = {}
        self.latest_spy_price = 0.0
        self.current_option_stream = None
        
        # Init Logger
        logging.basicConfig(filename='nexus_engine.log', level=logging.INFO, format='%(asctime)s %(message)s')
        
    def log_msg(self, m):
        print(m); logging.info(m)

    async def start_workers(self):
        self.log_msg("🔵 Nexus Engine Starting...")
        
        # Init TradeStation
        try:
            if TS_CLIENT_ID:
                self.TS = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_REFRESH_TOKEN, TS_ACCOUNT_ID)
                self.log_msg("✅ TradeStation Connected")
            else:
                self.log_msg("⚠️ No TS Credentials. Simulation Only.")
        except Exception as e:
            self.log_msg(f"❌ TS Connection Failed: {e}")

        # Start Loops
        asyncio.create_task(self.poll_account_data())
        asyncio.create_task(self.listen_for_execution())
        asyncio.create_task(self.stream_three_minute_bars())
        asyncio.create_task(self.listen_for_control())

    async def listen_for_execution(self):
        while True:
            try:
                msg = await self.exec_sock.recv_json()
                self.log_msg(f"📝 EXEC REQ: {msg}")
                
                # --- ORDER LOGIC ---
                # Expected msg: {"action": "BUY/SELL", "symbol": "XYZ", "quantity": 1, "type": "MARKET/LIMIT", "limit_price": 100.0}
                
                res = None
                if DRY_RUN_EXEC:
                    self.log_msg("🟢 DRY RUN EXECUTION")
                    res = {"id": "SIM_ORDER_123", "status": "Filled"}
                elif self.TS:
                    # BUILD PAYLOAD
                    action = msg.get("action", "").upper() # BUY or SELL
                    symbol = msg.get("symbol")
                    qty = int(msg.get("quantity", 1))
                    order_type = msg.get("type", "MARKET")
                    limit_price = msg.get("limit_price")
                    
                    # DETECT ASSET TYPE
                    # If symbol has numbers (e.g. SPY 231215C00450000), it's an option
                    is_option = any(char.isdigit() for char in symbol)
                    
                    ts_action = action
                    if is_option:
                        if action == "BUY": ts_action = "BuyToOpen"
                        elif action == "SELL": ts_action = "SellToClose"
                    else:
                        ts_action = action.title()
                        
                    payload = {
                        "AccountID": TS_ACCOUNT_ID,
                        "Symbol": symbol,
                        "Quantity": str(qty),
                        "OrderType": "Market" if order_type == "MARKET" else "Limit",
                        "TradeAction": ts_action,
                        "TimeInForce": {"Duration": "Day"},
                        "Route": "Intelligent"
                    }
                    
                    if order_type == "LIMIT" and limit_price:
                        payload["LimitPrice"] = str(limit_price)
                        
                    self.log_msg(f"🚀 SENDING ORDER: {payload}")
                    res = await asyncio.to_thread(self.TS.place_order, payload)
                
                if res and "Error" in res:
                     self.log_msg(f"❌ ORDER FAIL: {res}")
                     await self.exec_sock.send_json({"status": "error", "msg": res.get("Message")})
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
                mi.update("🟢 DRY RUN")
                mi.styles.background = "#008000"; mi.styles.color = "white"
            else:
                mi.update("🔴 LIVE TRADING")
                mi.styles.background = "#D90429"; mi.styles.color = "white"

            dt = self.query_one("#ticker_table", DataTable)
            dt.add_columns(" SYMBOL ", " LAST ", " CHG % ", " TIME "); dt.cursor_type = "none"
            for s in ALL_SYMBOLS: dt.add_row(s, "-", "-", "-")

            # Start Engine Workers
            self.run_worker(self.start_workers)

# --- HEADLESS RUNNER ---
async def run_headless_engine():
    print("🔵 STARTING HEADLESS ENGINE...")
    engine = NexusEngine()
    await engine.start_workers()

# --- MAIN ---
if __name__ == "__main__": 
    if "--simulation" in sys.argv:
        print("🔵 TS NEXUS SIMULATION MODE ACTIVE")
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
