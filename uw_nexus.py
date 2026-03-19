import os
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static, Log
from textual.containers import Vertical, Grid, Horizontal
from rich.text import Text
from textual import work
import asyncio, aiohttp, json, ssl, datetime, os
import sys

# --- ZMQ (for publishing) ---
try:
    import zmq
    import zmq.asyncio
    import numpy as np
except ImportError:
    print("="*50)
    print("ERROR: Missing required library 'pyzmq'.")
    print("Please install it by running:")
    print("pip3 install pyzmq")
    print("="*50)
    sys.exit(1)

# --- Timezone ---
try: 
    import pytz
    ET = pytz.timezone('US/Eastern')
except ImportError:
    print("="*50)
    print("ERROR: Missing required library 'pytz'.")
    print("Please install it by running:")
    print("pip3 install pytz")
    print("="*50)
    sys.exit(1)

# --- ============================== ---
# --- CONFIGURATION
# --- ============================== ---

# --- API Keys ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
UW_WS_URL = f"wss://api.unusualwhales.com/socket?token={UW_API_KEY}"

# --- ZMQ Port ---
# ts_nexus.py uses 5555, so this MUST be different.
ZMQ_PORT = 9999

# --- Channels to subscribe to ---
# Add or remove any channels you want to broadcast.
# Your other scripts can then subscribe to these "topics" from the ZMQ port.
CHANNELS_TO_JOIN = [
    # --- Global ---
    "flow-alerts",      # All flow alerts
    "news",             # Live headline news
    
    # --- SPY ---
    "price:SPY",        # SPY price updates
    "gex:SPY",          # SPY GEX (aggregate)
    "option_trades:SPY", # SPY option trades
    
    # --- SPX ---
    "price:$SPX.X",     # SPX price updates
    "gex:SPX",          # SPX GEX (aggregate)
    "option_trades:SPX" # SPX option trades
]
# ----------------------------------

class RollingStats:
    def __init__(self, window_days=30):
        self.window = datetime.timedelta(days=window_days)
        self.history = [] # List of (timestamp, value)

    def process(self, timestamp, value):
        # 1. Prune old data (Time-Based)
        cutoff = timestamp - self.window
        self.history = [x for x in self.history if x[0] > cutoff]
        
        # 2. Calculate Stats on PRIOR history (No Leakage)
        mean = 0.0
        std = 0.0
        z_score = 0.0
        
        if len(self.history) > 1:
            vals = [x[1] for x in self.history]
            mean = np.mean(vals)
            std = np.std(vals)
            if std > 0:
                z_score = (value - mean) / std
        
        # 3. Update History
        self.history.append((timestamp, value))
        
        return z_score, mean, std

class UWNexus(App):
    CSS = """
    Screen { background: $surface-darken-1; }
    #top_bar { dock: top; height: 3; background: $surface; border-bottom: solid $primary; padding: 0 1; }
    #status_bar { content-align: left middle; text-style: bold; width: 1fr; }
    #main_grid { grid-size: 1; grid-columns: 100%; height: 1fr; }
    #left_pane { height: 100%; }
    #channel_table { height: 4fr; background: $surface-darken-1; }
    Log { height: 1fr; border-top: solid $secondary; background: black; }
    """
    zmq_ctx = zmq.asyncio.Context()
    pub_socket = None
    
    # Rolling Stats
    stats_premium = RollingStats(window_days=30)
    stats_vol = RollingStats(window_days=30)

    def compose(self) -> ComposeResult:
        with Horizontal(id="top_bar"): 
            yield Static("Initializing...", id="status_bar")
        with Grid(id="main_grid"):
            with Vertical(id="left_pane"):
                yield DataTable(id="channel_table")
                yield Log(id="event_log")
    
    async def on_mount(self):
        # Bind the ZMQ Publisher socket
        self.pub_socket = self.zmq_ctx.socket(zmq.PUB)
        self.pub_socket.bind(f"tcp://*:{ZMQ_PORT}")
        
        # Setup the TUI table
        dt = self.query_one("#channel_table", DataTable)
        dt.add_columns(" CHANNEL ", " LAST MESSAGE ", " TIME "); dt.cursor_type = "none"
        for channel in CHANNELS_TO_JOIN: 
            dt.add_row(channel, "-", "-")
            
        self.log_msg(f"UW Nexus started. Broadcasting on port {ZMQ_PORT}")
        
        # Start the main WebSocket worker
        self.run_worker(self.start_uw_stream, exclusive=True, thread=True)

    async def on_unmount(self):
        if self.pub_socket: self.pub_socket.close()
        self.zmq_ctx.term()

    def update_status(self, t): 
        self.query_one("#status_bar", Static).update(Text.from_markup(t))
    
    def log_msg(self, m): 
        self.query_one(Log).write(f"[{datetime.datetime.now(ET).strftime('%H:%M:%S')}] {m}")

    def get_ssl_context(self): 
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    @work(exclusive=True)
    async def start_uw_stream(self):
        """
        Main worker loop. Connects to UW WebSocket and auto-reconnects.
        """
        # [HIBER-NATION] Import Schedule
        try: from nexus_config import is_market_open, get_et_now
        except: is_market_open = lambda: True

        while True:
            # 1. Check Schedule
            if not is_market_open():
                self.update_status("[blue]💤 HIBERNATING (Market Closed)[/]")
                self.log_msg("Market Closed. Sleeping for 5m...")
                await asyncio.sleep(300)
                continue

            # 2. Check Memory (Self-Healing)
            try:
                import resource
                # RUSAGE_SELF -> Max RSS in KB (Linux) or Bytes (Mac)
                # We assume Linux (KB). Limit = 2.5GB = 2.5 * 1024^2 KB = 2,621,440 KB
                mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                if mem > 2_621_440: 
                    self.log_msg(f"⚠️ HIGH MEMORY ({mem/1024:.1f} MB). Triggering Restart...")
                    sys.exit(0) # Watchdog will respawn us fresh
            except: pass

            try:
                self.update_status("[yellow]CONNECTING to UW...[/]")
                self.log_msg("Worker: Connecting to WebSocket...")
                
                ssl_ctx = self.get_ssl_context()
                
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
                    async with s.ws_connect(UW_WS_URL, ssl=ssl_ctx) as ws:
                        
                        self.update_status("[bold green]● UW NEXUS ACTIVE[/]")
                        self.log_msg("WebSocket connected. Joining channels...")

                        # --- Subscribe to channels ---
                        for channel in CHANNELS_TO_JOIN:
                            await ws.send_json({"channel": channel, "msg_type": "join"})
                            self.log_msg(f"Sent JOIN for: {channel}")

                        # --- Main message loop ---
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                # Handle the incoming data
                                await self.handle_message(msg.data)
                                
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                self.log_msg(f"WebSocket Error/Closed: {msg.data}")
                                break # Break inner loop to trigger reconnect
                        
            except Exception as e:
                self.log_msg(f"Worker Loop Error: {e}")
            
            # If we break the loop (error or disconnect), wait 5s and retry
            self.update_status(f"[red]STREAM LOST. Reconnecting in 5s...[/]")
            await asyncio.sleep(5)

    async def handle_message(self, raw_data: str):
        """
        Parses a message from UW and publishes it to ZMQ.
        """
        try:
            # UW data format is [<CHANNEL_NAME>, <PAYLOAD>]
            data_list = json.loads(raw_data)
            
            channel_name = data_list[0]
            payload = data_list[1]
            
            # Use the channel name as the ZMQ topic
            topic = channel_name.encode()
            
            # We broadcast the payload itself
            message = json.dumps(payload).encode()
            
            # --- Z-Score Calculation & Alerting ---
            try:
                # Only process flow-alerts for Z-Score
                if channel_name == "flow-alerts":
                    # Payload is a dict for flow-alerts
                    if isinstance(payload, dict):
                        prem = float(payload.get('premium') or payload.get('total_premium') or 0)
                        ts_raw = payload.get('executed_at') or payload.get('timestamp') or datetime.datetime.now(ET).timestamp()
                        
                        # Convert to datetime object for RollingStats
                        if isinstance(ts_raw, (int, float)):
                            ts_dt = datetime.datetime.fromtimestamp(ts_raw, tz=ET)
                        else:
                            ts_dt = datetime.datetime.now(ET)

                        # Calculate Z-Score
                        z_prem, _, _ = self.stats_premium.process(ts_dt, prem)
                        
                        # Check Thresholds
                        if z_prem > 4.0:
                            alert_msg = {
                                "type": "ALERT",
                                "z_score": z_prem,
                                "ticker": payload.get('ticker'),
                                "premium": prem,
                                "description": "Bearish Whale (High Z-Score)"
                            }
                            # Publish Alert
                            await self.pub_socket.send_multipart([b"system-alerts", json.dumps(alert_msg).encode()])
                            self.log_msg(f"🚨 SENT ALERT: Z={z_prem:.1f}")
                            
                        elif z_prem < -4.0:
                            alert_msg = {
                                "type": "ALERT",
                                "z_score": z_prem,
                                "ticker": payload.get('ticker'),
                                "premium": prem,
                                "description": "Bullish Whale (Low Z-Score)"
                            }
                            # Publish Alert
                            await self.pub_socket.send_multipart([b"system-alerts", json.dumps(alert_msg).encode()])
                            self.log_msg(f"🟢 SENT ALERT: Z={z_prem:.1f}")

            except Exception as e:
                self.log_msg(f"Logic Error: {e}")

            # --- Publish to ZMQ (Original Stream) ---
            await self.pub_socket.send_multipart([topic, message])
            
            # --- Update TUI Table ---
            try:
                dt = self.query_one("#channel_table", DataTable)
                try:
                    row_index = CHANNELS_TO_JOIN.index(channel_name)
                    # Just show that we got data. A full payload string is too long.
                    dt.update_cell_at((row_index, 1), f"Received payload")
                    dt.update_cell_at((row_index, 2), f" {datetime.datetime.now(ET).strftime('%H:%M:%S')} ")
                except ValueError:
                    pass # Channel not in our table, ignore
            except:
                pass # Headless mode or UI not ready
                
        except Exception as e:
            self.log_msg(f"Parse Error: {e} | Data: {raw_data[:100]}...")

if __name__ == "__main__":
    UWNexus().run()