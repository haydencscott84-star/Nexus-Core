import os
import asyncio
import zmq.asyncio
import json
import time
import datetime
import random
import requests
import ssl

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Log
from textual.containers import Container
from textual import on, work
from textual.message import Message
from rich.text import Text
from rich.panel import Panel

# --- CONFIGURATION ---
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY") 
SPX_TICKER = "$SPX.X"
SPY_TICKER = "SPY"
PRICE_ZMQ_PORT = 5555    # Nexus
PROFILER_FLOW_PORT = 5571 # Profiler

# --- SETTINGS ---
WALL_CHECK_INTERVAL = 3.0
FLOW_STRIKE_RANGE = 15.0
WALL_ACTIVATION_RANGE = 15.0  # INCREASED from 5.0 to 15.0 for better sensitivity

# --- GLOBAL STATE ---
LIVE_PRICE = 0.0
CURRENT_BASIS = 0.0 
LAST_GEX_WALLS = {'spx_put_wall': 0.0, 'spx_call_wall': 0.0}
LAST_FILE_READ_TIME = 0.0 # New global for throttling file reads
LATEST_FLOW_DATA = [] 
CURRENT_ACTIVE_WALL_STRIKE = 0.0

# --- UTILS ---
def fmt_num(val): 
    return f"${val/1e6:.1f}M" if abs(val)>=1e6 else (f"${val/1e3:.0f}K" if abs(val)>=1e3 else f"${val:.0f}")

# --- SYNC WORKER FUNCTION ---
def fetch_zone_flow_sync(target_strike: float, target_dte: int):
    """Fetches aggregated flow from Unusual Whales (Blocking Sync Call)."""
    min_stk = target_strike - FLOW_STRIKE_RANGE
    max_stk = target_strike + FLOW_STRIKE_RANGE
    
    url = f"https://api.unusualwhales.com/api/stock/SPX/flow-per-strike"
    params = {
        'min_strike': min_stk,
        'max_strike': max_stk,
        'max_dte': target_dte + 5,
        'date': datetime.datetime.now().strftime('%Y-%m-%d')
    }
    headers = {"Authorization": f"Bearer {UW_API_KEY}"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        
        total_call_prem = 0.0
        total_put_prem = 0.0
        
        for strike_data in data.get('data', []):
            total_call_prem += float(strike_data.get('call_premium', 0) or 0)
            total_put_prem += float(strike_data.get('put_premium', 0) or 0)
            
        return {'call_prem': total_call_prem, 'put_prem': total_put_prem}
        
    except Exception:
        return None

# --- CUSTOM EVENTS ---
class CheckWallEvent(Message): pass

# --- WIDGETS ---
class AggregationDisplay(Static):
    def update_content(self, results):
        call_prem = results['call_prem']
        put_prem = results['put_prem']
        net_prem = call_prem - put_prem
        
        t = Panel(
            Text.from_markup(
                f"CALL PREMIUM (BULL): [green]{fmt_num(call_prem)}[/]\n"
                f"PUT PREMIUM (BEAR): [red]{fmt_num(put_prem)}[/]\n"
                f"NET FLOW: [{'green' if net_prem > 0 else 'red'}]{fmt_num(net_prem)}[/]"
            ), 
            title="[bold yellow]Zone Aggregation[/]"
        )
        self.update(t)

# --- MAIN APP ---
class MultiTapeViewer(App):
    CSS = """
    Screen { background: $surface; }
    Header { dock: top; background: $surface-darken-1; }
    #wall-status { dock: top; height: 3; content-align: center middle; text-style: bold; }
    #wall-status.active { background: $error-darken-1; color: white; }
    #wall-status.inactive { background: $secondary; color: $text; }
    #aggregation-container { height: 1fr; }
    #app-log { dock: bottom; height: 8; background: $surface-darken-1; }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Status: Waiting for Walls...", id="wall-status", classes="inactive")
        with Container(id="aggregation-container"):
            yield AggregationDisplay(id="agg-display")
            yield Static("Waiting for Zone Activation...")
        yield Log(id="app-log")
        yield Footer()

    async def on_mount(self):
        self.log_msg("Starting Live Tape Viewer (Optimized)...")
        
        # Start ZMQ Listeners as background tasks
        self.zmq_ctx = zmq.asyncio.Context()
        asyncio.create_task(self.listen_to_prices())
        asyncio.create_task(self.listen_to_flow())
        
        # Start the Worker
        self.run_worker(self.fetch_flow_worker, exclusive=False, thread=True)

    def log_msg(self, m: str): 
        self.query_one(Log).write(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {m}")

    # --- ZMQ TASK 1: PRICES ---
    async def listen_to_prices(self):
        sock = self.zmq_ctx.socket(zmq.SUB)
        try:
            sock.connect(f"tcp://127.0.0.1:{PRICE_ZMQ_PORT}")
            sock.subscribe(SPX_TICKER.encode('utf-8'))
            sock.subscribe(SPY_TICKER.encode('utf-8'))
            self.log_msg(f"Connected to Price Stream on {PRICE_ZMQ_PORT}")
        except Exception as e:
            self.log_msg(f"Price ZMQ Error: {e}")
            return

        while True:
            topic, msg = await sock.recv_multipart()
            data = json.loads(msg)
            topic_str = topic.decode('utf-8')
            
            if topic_str == SPX_TICKER and "Last" in data:
                global LIVE_PRICE; LIVE_PRICE = float(data['Last'])
                # Trigger wall check on every price update
                self.post_message(CheckWallEvent())
            
            elif topic_str == SPY_TICKER and "Last" in data:
                global CURRENT_BASIS
                if LIVE_PRICE > 0: 
                    CURRENT_BASIS = LIVE_PRICE - (float(data['Last']) * 10)

    # --- ZMQ TASK 2: FLOW ---
    async def listen_to_flow(self):
        sock = self.zmq_ctx.socket(zmq.SUB)
        try:
            sock.connect(f"tcp://127.0.0.1:{PROFILER_FLOW_PORT}")
            sock.subscribe(b"SPX_FLOW")
            sock.subscribe(b"SPY_FLOW")
            self.log_msg(f"Connected to Flow Stream on {PROFILER_FLOW_PORT}")
        except Exception as e:
            self.log_msg(f"Flow ZMQ Error: {e}")
            return

        while True:
            topic, msg = await sock.recv_multipart()
            data = json.loads(msg)
            
            global LATEST_FLOW_DATA
            LATEST_FLOW_DATA = data

    # --- LOGIC: WALL CHECKER ---
    @on(CheckWallEvent)
    def check_walls_and_trigger(self):
        global CURRENT_ACTIVE_WALL_STRIKE
        global LAST_GEX_WALLS
        global LAST_FILE_READ_TIME
        
        # --- OPTIMIZATION: Only read file every 60 seconds ---
        current_time = time.time()
        if current_time - LAST_FILE_READ_TIME > 60.0:
            try:
                with open("market_levels.json", 'r') as f:
                    data = json.load(f)
                    LAST_GEX_WALLS['spx_put_wall'] = data.get('spx_put_wall', 0.0)
                    LAST_GEX_WALLS['spx_call_wall'] = data.get('spx_call_wall', 0.0)
                    LAST_FILE_READ_TIME = current_time
                    self.log_msg(f"SYSTEM: Updated Walls -> Put: {LAST_GEX_WALLS['spx_put_wall']} / Call: {LAST_GEX_WALLS['spx_call_wall']}")
            except Exception:
                 pass # If file busy or missing, skip this cycle
        
        current_price = LIVE_PRICE
        put_wall = LAST_GEX_WALLS['spx_put_wall']
        call_wall = LAST_GEX_WALLS['spx_call_wall']
        
        if current_price == 0: return

        active_wall_strike = 0.0
        wall_type = None

        # Calculate Distances
        dist_to_put = abs(current_price - put_wall)
        dist_to_call = abs(current_price - call_wall)

        # Check Distance to Walls (Using wider WALL_ACTIVATION_RANGE)
        if put_wall > 500 and dist_to_put <= WALL_ACTIVATION_RANGE:
            active_wall_strike = put_wall
            wall_type = "Put Wall (Support)"
        elif call_wall > 500 and dist_to_call <= WALL_ACTIVATION_RANGE:
            active_wall_strike = call_wall
            wall_type = "Call Wall (Resistance)"
            
        # State Transition Logic
        if active_wall_strike > 0.0:
            # If we are entering a zone or switching zones
            if CURRENT_ACTIVE_WALL_STRIKE != active_wall_strike:
                self.log_msg(f"TRIGGER: Activating flow fetch near {wall_type} ${active_wall_strike:.0f}")
            
            CURRENT_ACTIVE_WALL_STRIKE = active_wall_strike
            status_text = f"ACTIVE: Price ${current_price:.2f} in Zone: {wall_type} ${active_wall_strike:.0f} (Dist: {min(dist_to_put, dist_to_call):.1f})"
            
            # Update status
            self.query_one("#wall-status").update(status_text)
            self.query_one("#wall-status").set_class("active")
            
        else:
            # Leaving the zone
            if CURRENT_ACTIVE_WALL_STRIKE != 0.0:
                self.log_msg("IDLE: Price left the wall zone. Stopping flow fetch.")
            
            CURRENT_ACTIVE_WALL_STRIKE = 0.0
            
            # Show distance in IDLE status so we know why it's not triggering
            closest_dist = dist_to_put if dist_to_put < dist_to_call else dist_to_call
            target_wall = "Put" if dist_to_put < dist_to_call else "Call"
            
            status_text = f"IDLE: ${current_price:.2f} | {target_wall} Dist: {closest_dist:.2f} (Needs < {WALL_ACTIVATION_RANGE})"
            
            self.query_one("#wall-status").update(status_text)
            self.query_one("#wall-status").set_class("inactive")

    # --- LOGIC: FLOW FETCHER WORKER ---
    @work(exclusive=True, thread=True)
    async def fetch_flow_worker(self):
        BASE_INTERVAL = 30.0 
        MAX_VARIATION = 5.0 
        
        while True:
            # Sleep Calculation
            random_offset = random.uniform(-MAX_VARIATION, MAX_VARIATION)
            sleep_time = BASE_INTERVAL + random_offset
            
            if CURRENT_ACTIVE_WALL_STRIKE != 0.0:
                try:
                    target_dte = 3 
                    if LATEST_FLOW_DATA: 
                        min_dte_list = [r['dte'] for r in LATEST_FLOW_DATA if r.get('dte') is not None and r['dte'] >= 0]
                        if min_dte_list: target_dte = min(min_dte_list)
                    
                    self.call_from_thread(self.log_msg, f"FETCH: Polling flow (DTE {target_dte}, Zone $\\pm{FLOW_STRIKE_RANGE:.0f})...")
                    
                    results = fetch_zone_flow_sync(CURRENT_ACTIVE_WALL_STRIKE, target_dte)
                    
                    if results:
                        self.call_from_thread(self.query_one(AggregationDisplay).update_content, results)
                        net = results['call_prem'] - results['put_prem']
                        self.call_from_thread(self.log_msg, f"FLOW UPDATED: Net {fmt_num(net)}")
                    
                    await asyncio.sleep(sleep_time)
                except Exception as e:
                    self.call_from_thread(self.log_msg, f"FETCH ERROR: {e}")
                    await asyncio.sleep(60) 
            else:
                # Idle wait
                await asyncio.sleep(WALL_CHECK_INTERVAL)

if __name__ == "__main__":
    MultiTapeViewer().run()