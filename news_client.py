import asyncio
import json
import sys
import datetime
import re
from typing import Set

# --- ZMQ ---
try:
    import zmq
    import zmq.asyncio
except ImportError:
    print("=" * 50)
    print("ERROR: Missing required library 'pyzmq'.")
    print("Please install it by running:")
    print("pip3 install pyzmq")
    print("=" * 50)
    sys.exit(1)

# --- Textual ---
try:
    from textual.app import App, ComposeResult
    from textual.widgets import Header, Footer, DataTable
    from textual import work
    from rich.text import Text
except ImportError:
    print("=" * 50)
    print("ERROR: Missing required library 'textual'.")
    print("Please install it by running:")
    print("pip3 install textual")
    print("=" * 50)
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

# This MUST match the port in uw_nexus.py
ZMQ_PORT = 5556

# This is the ZMQ topic to subscribe to (from the 'news' channel in uw_nexus.py)
ZMQ_TOPIC = b"news"

# The master list of tickers we care about.
# Using a Set for very fast lookups.
TARGET_TICKERS: Set[str] = {
    # --- User's Core List ---
    "SPY", 
    "SPX", 
    "VIX", 
    "@ES", 
    "@NQ",
    
    # --- Top 100 Tickers (S&P 100) ---
    "AAPL", "MSFT", "NVDA", "GOOG", "GOOGL", "AMZN", "META", "BRK-B", "LLY", "TSLA",
    "AVGO", "V", "JPM", "WMT", "XOM", "UNH", "MA", "PG", "JNJ", "COST", 
    "HD", "MRK", "ORCL", "CVX", "CRM", "BAC", "NFLX", "AMD", "KO", "ADBE",
    "PEP", "LIN", "TMO", "ABBV", "WFC", "CSCO", "MCD", "DIS", "QCOM", "CAT",
    "GE", "INTC", "IBM", "AMAT", "NOW", "UBER", "INTU", "AXP", "PM", "ISRG",
    "AMGN", "PFE", "COP", "TXN", "HON", "BA", "MS", "RTX", "SBUX", "SCHW",
    "LRCX", "GS", "BLK", "PLD", "ETN", "ELV", "SYK", "MMM", "ABT", "ACN",
    "AIG", "AEP", "BIIB", "BMY", "C", "CL", "CMCSA", "COF", "DE", "DUK",
    "GILD", "LOW", "MO", "NEE", "PYPL", "SO", "T", "TGT", "UPS", "USB", "VZ"
}
# ----------------------------------

class NewsFeedClient(App):
    """
    A Textual app that subscribes to the uw_nexus ZMQ feed
    and filters for news related to a target list of tickers.
    """
    
    CSS = """
    Screen {
        layout: vertical;
    }
    Header {
        dock: top;
    }
    Footer {
        dock: bottom;
    }
    DataTable {
        height: 1fr;
        width: 1fr;
        border: solid $secondary;
    }
    """
    
    BINDINGS = [("q", "quit", "Quit")]
    
    # ZMQ setup
    zmq_ctx = zmq.asyncio.Context()
    sub_socket = None

    def compose(self) -> ComposeResult:
        yield Header("Nexus News Squawk Box")
        yield DataTable(id="news_table", zebra_stripes=True)
        yield Footer()

    async def on_mount(self):
        """Called when the app is first mounted."""
        table = self.query_one(DataTable)
        table.add_columns("TIME", "TICKER", "SENT", "HEADLINE")
        
        # Start the background worker
        self.run_worker(self.subscribe_to_news, exclusive=True, thread=True)

    async def on_unmount(self):
        """Called when the app is shutting down."""
        if self.sub_socket:
            self.sub_socket.close()
        self.zmq_ctx.term()

    def get_current_time(self) -> str:
        """Helper to get a formatted timestamp."""
        return datetime.datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S')

    @work(exclusive=True, thread=True)
    async def subscribe_to_news(self):
        """The main ZMQ subscription worker."""
        table = self.query_one(DataTable)
        
        try:
            self.sub_socket = self.zmq_ctx.socket(zmq.SUB)
            self.sub_socket.setsockopt(zmq.LINGER, 0)
            self.sub_socket.connect(f"tcp://localhost:{ZMQ_PORT}")
            self.sub_socket.subscribe(ZMQ_TOPIC)
            
            while True:
                try:
                    # Wait for a multipart message
                    msg = await self.sub_socket.recv_multipart()
                    if len(msg) < 2 or not msg[1]: continue

                    topic = msg[0]
                    message = msg[1]
                    
                    # We only subscribed to "news", but good to be safe.
                    if topic == ZMQ_TOPIC:
                        payload = json.loads(message.decode())
                        
                        # This is the core filtering logic
                        news_tickers = set(payload.get("tickers", []))
                        
                        # Check for any overlap between news_tickers and our target list
                        matched_tickers = TARGET_TICKERS.intersection(news_tickers)
                        
                        if matched_tickers:
                            # We have a match!
                            headline = payload.get('headline', 'No Headline')
                            source = payload.get('source', 'unknown')
                            ts_raw = payload.get('created_at') or datetime.datetime.now(ET).timestamp()
                            
                            # 1. Time Formatting
                            if isinstance(ts_raw, (int, float)):
                                ts_dt = datetime.datetime.fromtimestamp(ts_raw, tz=ET)
                            else:
                                ts_dt = datetime.datetime.now(ET)
                            time_str = ts_dt.strftime('%I:%M %p')
                            
                            # 2. Ticker Formatting
                            ticker_str = ", ".join(sorted(list(matched_tickers)))
                            ticker_render = Text(ticker_str, style="bold cyan")
                            
                            # 3. Headline Formatting (Keywords)
                            keywords = ["CHINA", "OIL", "WAR", "TRUMP", "FED"]
                            headline_render = Text(headline)
                            for kw in keywords:
                                if kw in headline.upper():
                                    headline_render.highlight_regex(kw, "bold yellow")
                                    # Also ensure case-insensitive match highlights correctly if needed, 
                                    # but highlight_regex is usually case-sensitive by default. 
                                    # Let's use a regex with ignorecase flag if we want.
                                    # For now, simple regex:
                                    import re
                                    headline_render.highlight_regex(f"(?i){kw}", "bold yellow")

                            # 4. Sentiment (Placeholder)
                            sent = payload.get('sentiment', '-')
                            sent_style = "green" if sent == "POSITIVE" else ("red" if sent == "NEGATIVE" else "dim")
                            sent_render = Text(sent, style=sent_style)

                            # Add Row
                            self.call_from_thread(table.add_row, time_str, ticker_render, sent_render, headline_render)
                            self.call_from_thread(table.scroll_end, animate=False)

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    await asyncio.sleep(1) # Avoid spamming errors

        except Exception as e:
            pass


if __name__ == "__main__":
    if "--headless" in sys.argv:
        print("Starting News Client in HEADLESS mode (Log Only)...")
        # Run just the background worker logic manually
        # Since the class logic is tightly coupled to Textual, we'll create a simple loop utilizing the same ZMQ logic.
        
        ctx = zmq.asyncio.Context()
        sock = ctx.socket(zmq.SUB)
        sock.setsockopt(zmq.LINGER, 0)
        sock.connect(f"tcp://localhost:{ZMQ_PORT}")
        sock.subscribe(ZMQ_TOPIC)
        
        import asyncio
        
        async def headless_loop():
            print(f"HEADLESS: Subscribed to {ZMQ_TOPIC} on {ZMQ_PORT}")
            while True:
                try:
                    msg = await sock.recv_multipart()
                    if len(msg) < 2: continue
                    message = msg[1]
                    payload = json.loads(message.decode())
                    
                    news_tickers = set(payload.get("tickers", []))
                    matched_tickers = TARGET_TICKERS.intersection(news_tickers)
                    
                    if matched_tickers:
                        headline = payload.get('headline', 'No Headline')
                        t_str = ",".join(matched_tickers)
                        print(f"[NEWS] {t_str}: {headline}")
                        
                except Exception as e:
                    print(f"Error: {e}")
                    await asyncio.sleep(1)
                    
        try:
            asyncio.run(headless_loop())
        except KeyboardInterrupt:
            print("Stopping...")
    else:
        NewsFeedClient().run()