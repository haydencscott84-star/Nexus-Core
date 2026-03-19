"""
Live Intraday Options Indicators TUI (OBV & VWAP)

This script connects to *both* the ts_nexus and uw_nexus services
to create real-time, options-based On-Balance Volume (OBV)
and Volume-Weighted Average Price (VWAP) indicators.

--- MODIFIED: Updated to use 'Digits' widgets for large display ---
"""

# --- Core Python / TUI ---
import asyncio
import datetime
import os
import json
import ssl
import sys
from datetime import timedelta, time as dt_time
from collections import deque

# --- ZMQ (for subscribing) ---
try:
    import zmq
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

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Log, Digits
from textual.containers import Grid, Vertical
from rich.text import Text
from rich.panel import Panel
from textual import work
from textual.reactive import reactive

# --- ============================== ---
# --- 1. CONFIGURATION
# --- ============================== ---

# --- Nexus Ports ---
TS_NEXUS_PORT = 5555
UW_NEXUS_PORT = 5556

# --- Tickers / Topics ---
TICKER_PRICE = "SPY"
TICKER_TRADES = "option_trades:SPY"

# --- Polling Timer Config ---
POLL_FAST_TICK_SECONDS = 0.5

# --- ============================== ---
# --- 2. TUI WIDGETS
# --- ============================== ---

class HeaderBox(Static):
    """A simple header box with the app title and status."""
    
    zmq_status = reactive("CONNECTING...")
    
    def render(self) -> Text:
        status_style = "green" if self.zmq_status == "CONNECTED" else "red"
        return Text.from_markup(
            f" [bold]Live Intraday Options Indicators (OBV/VWAP)[/] | "
            f"ZMQ Status: [{status_style}]{self.zmq_status}[/]"
        )

class PriceBox(Vertical):
    """Displays the live price using Digits."""
    
    def compose(self) -> ComposeResult:
        yield Static(f"{TICKER_PRICE} Price", classes="label")
        yield Digits("0.00", id="price_digits")
        yield Static("---%", id="pct_label", classes="sub-label")

    def on_mount(self):
        self.set_interval(POLL_FAST_TICK_SECONDS, self.update_price)
        
    def update_price(self): 
        price = self.app.live_price
        pct = self.app.price_change_pct
        
        style = "green" if pct >= 0 else "red"
        
        # Update Digits
        digits = self.query_one("#price_digits", Digits)
        digits.update(f"${price:,.2f}")
        digits.styles.color = style
        
        # Update Pct Label
        label = self.query_one("#pct_label", Static)
        label.update(f"{pct:+.2f}%")
        label.styles.color = style

class OBVBox(Vertical):
    """Displays the live Options OBV using Digits."""

    def compose(self) -> ComposeResult:
        yield Static("Options OBV", classes="label")
        yield Digits("0", id="obv_digits")
        yield Static("(0)", id="chg_label", classes="sub-label")
    
    def on_mount(self):
        self.set_interval(POLL_FAST_TICK_SECONDS, self.update_obv)

    def update_obv(self): 
        obv = self.app.options_obv
        last_change = self.app.last_obv_change
        
        obv_style = "green" if obv >= 0 else "red"
        change_style = "green" if last_change >= 0 else "red"
        
        # Update Digits
        digits = self.query_one("#obv_digits", Digits)
        digits.update(f"{obv:,}") # Commas for thousands
        digits.styles.color = obv_style
        
        # Update Change Label
        label = self.query_one("#chg_label", Static)
        label.update(f"Last: {last_change:+}")
        label.styles.color = change_style

class VWAPBox(Vertical):
    """Displays the live Options VWAP using Digits."""

    def compose(self) -> ComposeResult:
        yield Static("Options VWAP", classes="label")
        yield Digits("0.00", id="vwap_digits")
        yield Static("Waiting...", id="status_label", classes="sub-label")
    
    def on_mount(self):
        self.set_interval(POLL_FAST_TICK_SECONDS, self.update_vwap)

    def update_vwap(self): 
        vwap = self.app.options_vwap
        price = self.app.live_price
        
        if vwap == 0.0:
            return

        # Style based on Price relative to VWAP
        # If Price > VWAP, VWAP acts as support (Green context)
        # If Price < VWAP, VWAP acts as resistance (Red context)
        style = "green" if price >= vwap else "red"
        status_text = "SUPPORT" if price >= vwap else "RESISTANCE"
        
        # Update Digits
        digits = self.query_one("#vwap_digits", Digits)
        digits.update(f"${vwap:.2f}")
        digits.styles.color = style
        
        # Update Label
        label = self.query_one("#status_label", Static)
        label.update(status_text)
        label.styles.color = "white"


# --- ============================== ---
# --- 3. MAIN APPLICATION
# --- ============================== ---

class OptionsOBVApp(App):
    """A TUI to display live Options OBV & VWAP."""
    
    CSS = """
    Screen {
        layout: grid;
        grid-size: 3;
        grid-rows: 3 1fr 8;
        background: #0f1219;
    }
    
    HeaderBox {
        column-span: 3;
        width: 100%;
        height: 100%;
        content-align: center middle;
        background: $surface-darken-1;
        border-bottom: solid $primary;
    }
    
    /* CONTAINER STYLING */
    PriceBox, OBVBox, VWAPBox {
        width: 100%;
        height: 100%;
        align: center middle;
        border: tall #3b4252;
        background: #1a1f2e;
        padding: 1;
    }
    
    /* TEXT STYLING */
    .label {
        text-align: center;
        color: #88c0d0;
        text-style: bold;
        dock: top;
        margin-bottom: 1;
    }
    
    .sub-label {
        text-align: center;
        dock: bottom;
        text-style: bold;
        opacity: 0.8;
    }

    /* DIGITS STYLING */
    Digits {
        width: 100%;
        text-align: center;
        content-align: center middle;
        height: 1fr;
    }

    Log {
        column-span: 3;
        width: 100%;
        height: 100%;
        border-top: solid $secondary;
        background: $surface;
    }
    """
    
    # --- APP STATE ---
    live_price = 0.0
    price_change_pct = 0.0
    options_obv = 0
    last_obv_change = 0
    
    total_premium_traded = 0.0
    total_volume_traded = 0
    options_vwap = 0.0
    
    def compose(self) -> ComposeResult:
        yield HeaderBox()
        yield PriceBox()
        yield OBVBox()
        yield VWAPBox()
        yield Log()
        yield Footer()

    def on_mount(self):
        self.log_msg("Starting ZMQ listeners...")
        self.run_worker(self.stream_data_from_nexus, exclusive=True, thread=True)
    
    def set_zmq_status(self, status: str):
        """Safely sets the ZMQ status in the HeaderBox from a thread."""
        try:
            self.query_one(HeaderBox).zmq_status = status
        except Exception as e:
            self.log_msg(f"HeaderBox update error: {e}")

    def log_msg(self, msg: str):
        self.query_one(Log).write(f"[{datetime.datetime.now(ET).strftime('%H:%M:%S')}] {msg}")

    def handle_price_tick(self, msg: list):
        """Called from worker when a TS price tick arrives."""
        try:
            payload = json.loads(msg[1].decode())
            
            # 1. Get the 'Last' price
            current_price = float(payload.get('Last', 0.0))
            if current_price > 0:
                self.live_price = current_price

            # 2. Get the NetChangePct (change from previous close)
            net_change_pct = float(payload.get('NetChangePct', 0.0))
            self.price_change_pct = net_change_pct
            
        except Exception as e:
            self.log_msg(f"Price Tick Error: {e}")
            
    def handle_trade_tick(self, msg: list):
        """Called from worker when a UW trade tick arrives."""
        try:
            trade = json.loads(msg[1].decode())

            size = int(trade.get('size', 0))    
            option_type = trade.get('option_type')
            tags = trade.get('tags', []) 
            
            if size == 0:
                return

            # --- 1. OBV Logic ---
            obv_change = 0
            if option_type and option_type.upper() == 'CALL':
                if 'ask_side' in tags:
                    obv_change = size # Bullish
                elif 'bid_side' in tags:
                    obv_change = -size # Bearish
            elif option_type and option_type.upper() == 'PUT':
                if 'ask_side' in tags:
                    obv_change = -size # Bearish
                elif 'bid_side' in tags:
                    obv_change = size # Bullish
            
            if obv_change != 0:
                self.options_obv += obv_change
                self.last_obv_change = obv_change

            # --- 2. VWAP Logic ---
            trade_price = float(trade.get('price', 0))
            trade_premium = trade_price * size
            
            self.total_premium_traded += trade_premium
            self.total_volume_traded += size
            
            if self.total_volume_traded > 0:
                self.options_vwap = self.total_premium_traded / self.total_volume_traded
                
        except Exception as e:
            self.log_msg(f"Trade Tick Error: {e} | Data: {msg[1][:100]}")

    @work(exclusive=True, thread=True)
    def stream_data_from_nexus(self):
        """
        Listens to *both* nexus broadcasters at the same time
        using a ZMQ Poller. This is a blocking function.
        """
        ctx = zmq.Context()
        poller = zmq.Poller()
        
        try:
            # 1. Connect to ts_nexus (Price)
            self.log_msg(f"Connecting to ts_nexus on port {TS_NEXUS_PORT}...")
            ts_sock = ctx.socket(zmq.SUB)
            ts_sock.connect(f"tcp://localhost:{TS_NEXUS_PORT}")
            ts_sock.setsockopt_string(zmq.SUBSCRIBE, TICKER_PRICE)
            poller.register(ts_sock, zmq.POLLIN)
            self.log_msg(f"Subscribed to topic: {TICKER_PRICE}")

            # 2. Connect to uw_nexus (Trades)
            self.log_msg(f"Connecting to uw_nexus on port {UW_NEXUS_PORT}...")
            uw_sock = ctx.socket(zmq.SUB)
            uw_sock.connect(f"tcp://localhost:{UW_NEXUS_PORT}")
            uw_sock.setsockopt_string(zmq.SUBSCRIBE, TICKER_TRADES)
            poller.register(uw_sock, zmq.POLLIN)
            self.log_msg(f"Subscribed to topic: {TICKER_TRADES}")
            
            self.call_from_thread(self.set_zmq_status, "CONNECTED")
            
            # 3. Start the listening loop
            while True:
                socks = dict(poller.poll()) # Blocks until a message arrives
                
                if ts_sock in socks:
                    msg = ts_sock.recv_multipart()
                    self.call_from_thread(self.handle_price_tick, msg)
                    
                if uw_sock in socks:
                    msg = uw_sock.recv_multipart()
                    self.call_from_thread(self.handle_trade_tick, msg)
        
        except Exception as e:
            self.log_msg(f"ZMQ Worker CRASH: {e}")
            self.call_from_thread(self.set_zmq_status, "ERROR")
        finally:
            poller.unregister(ts_sock)
            poller.unregister(uw_sock)
            ts_sock.close()
            uw_sock.close()
            ctx.term()

if __name__ == "__main__":
    OptionsOBVApp().run()