import pandas as pd
import numpy as np
import asyncio
import os
import sys
import json
import requests
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Button, Static, DataTable, Label
from rich.text import Text

try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except ImportError:
    TS_CLIENT_ID = ""
    TS_CLIENT_SECRET = ""
    TS_ACCOUNT_ID = ""

# --- CONFIGURATION ---
TICKER = "SPY"
YEARS_BACK = 2
SMA_PERIOD = 200 # 200 Hourly Bars
TARGET_WIN_RATE = 70.0
STATE_FILE = "reversion_hourly_state.json"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")

class ReversionHourlyApp(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #1e1e1e;
    }
    Header {
        dock: top;
        background: #4b0082; /* Indigo for Hourly */
        color: white;
        height: 3;
    }
    #controls {
        height: 5;
        dock: bottom;
        background: #2e2e2e;
        padding: 1;
        align: center middle;
    }
    Button {
        width: 30;
        background: #8800ff;
    }
    Label {
        padding: 1;
        background: #333;
        color: cyan;
        width: 100%;
        text-align: center;
        text-style: bold;
    }
    DataTable {
        height: auto;
    }
    """
    
    TITLE = f"Nexus Reversion HOURLY: {TICKER} (Swing)"
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with VerticalScroll():
            yield Static(f"PROTOCOL: Seeking >{TARGET_WIN_RATE}% Win Rate on Hourly 200 SMA Extensions", id="protocol_lbl")
            
            # Upside
            yield Label("🐻 SWING SHORT (Price > SMA 200)")
            yield DataTable(id="table_upside")
            
            # Downside
            yield Label("🐮 SWING LONG (Price < SMA 200)")
            yield DataTable(id="table_downside")
            
            yield Static("", id="status_lbl")

        with Horizontal(id="controls"):
            yield Button("REFRESH DATA", id="btn_refresh", variant="primary")

    def on_mount(self) -> None:
        self.init_tables()
        self.load_state()

    def init_tables(self):
        # COLUMNS for Hourly
        cols = ["Condition", "Samples", "1 Day (7h)", "2 Days", "3 Days", "1 Week"]
        
        t1 = self.query_one("#table_upside", DataTable)
        t1.add_columns(*cols)
        t1.cursor_type = "row"
        
        t2 = self.query_one("#table_downside", DataTable)
        t2.add_columns(*cols)
        t2.cursor_type = "row"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_refresh":
            self.run_analysis()

    def load_state(self):
        if not os.path.exists(STATE_FILE):
            self.query_one("#status_lbl").update("⚠️ No previous state found. Please Refresh.")
            return

        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            self.populate_table("#table_upside", state.get("bear", []))
            self.populate_table("#table_downside", state.get("bull", []))
            
            last_upd = state.get("last_updated", "Unknown")
            curr_ext = state.get("current_ext", 0.0)
            
            self.query_one("#status_lbl").update(f"✅ State Loaded from: {last_upd} (Ext: {curr_ext:.2f}%)")
            self.title = f"Nexus Reversion HOURLY: {TICKER} (Last: {last_upd})"
            
        except Exception as e:
            self.query_one("#status_lbl").update(f"❌ Load Error: {e}")

    def populate_table(self, table_id, rows):
        table = self.query_one(table_id, DataTable)
        table.clear()
        
        def get_style(rate):
            if rate >= 80: return "bold green"
            if rate >= 70: return "green"
            if rate >= 60: return "yellow"
            return "dim red"

        for r in rows:
            # Handle Dictionary Row
            is_curr = r.get('is_current', False)
            base_style = "bold cyan" if is_curr else "white"
            label = f"👉 {r['Condition']}" if is_curr else r['Condition']
            
            cells = [Text(label, style=base_style), Text(r['Samples'], style="dim white")]
            
            # Windows: 7h, 14h, 21h, 35h
            for w in [7, 14, 21, 35]:
                key = f"{w}hr"
                val = r.get(key, 0)
                cells.append(Text(f"{val:.0f}%", style=get_style(val)))
            
            table.add_row(*cells)

    def run_analysis(self):
        self.query_one("#status_lbl").update("⏳ Fetching 2 Years of Hourly Data...")
        self.run_worker(self.async_analysis(), exclusive=True)

    async def async_analysis(self):
        try:
            ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
            # 7 bars * 252 days * 2 years + buffer
            bars_needed = (7 * 252 * YEARS_BACK) + SMA_PERIOD + 100
             # FETCH 60-MINUTE BARS
            candles = ts.get_historical_data(TICKER, unit="Minute", interval="60", bars_back=str(bars_needed))
            
            # Fetch Live Price
            quote = ts.get_quote_snapshot(TICKER)
            try: current_price = float(quote.get('Last') or quote.get('Ask') or 0)
            except: current_price = 0

            if not candles:
                self.query_one("#status_lbl").update("❌ Error: No API Data Returned")
                return
                
            df = pd.DataFrame(candles)
            date_col = 'TimeStamp' if 'TimeStamp' in df.columns else 'Timestamp'
            df['Close'] = pd.to_numeric(df['Close'])
            df['Date'] = pd.to_datetime(df[date_col])
            df = df.sort_values('Date')
            
            # Use last close if live price failed
            if current_price == 0: current_price = float(df['Close'].iloc[-1])

            bull, bear, alert, curr_ext = self.process_data(df, current_price)
            self.update_ui(bull, bear, curr_ext)
            
            # Save State
            state = {"bull": bull, "bear": bear, "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "current_ext": curr_ext}
            with open(STATE_FILE, "w") as f: json.dump(state, f)
                
            if alert:
                requests.post(DISCORD_WEBHOOK, json={"content": alert})
                self.notify("Hourly Alert Sent", severity="information")
            else:
                self.notify(f"No Hourly Alerts (Ext: {curr_ext:.2f}%)", severity="warning")

        except Exception as e:
            self.query_one("#status_lbl").update(f"❌ Analysis Error: {e}")

    def process_data(self, df, current_price):
        # Indicators
        df['SMA_200'] = df['Close'].rolling(window=SMA_PERIOD).mean()
        df['Ext_Pct'] = ((df['Close'] - df['SMA_200']) / df['SMA_200']) * 100
        
        # Current Extension
        current_sma = df['SMA_200'].iloc[-1]
        current_ext = ((current_price - current_sma) / current_sma) * 100
        
        # Windows: 7h, 14h, 21h, 35h
        windows = [7, 14, 21, 35] 
        results_bull = []
        results_bear = []
        alert_msg = ""

        # Matrices
        for threshold in np.arange(1.0, 10.0, 0.5):
            # Upside (Short Signal)
            subset = df[df['Ext_Pct'] >= threshold]
            label = f"+{threshold:.1f}%"
            is_current = (current_ext >= threshold) and (current_ext < threshold + 0.5)
            
            count = len(subset)
            if count >= 10:
                row = {"Condition": label, "Samples": str(count), "is_current": bool(is_current)}
                high_prob = False
                for w in windows:
                     win_rate = (subset['Close'].shift(-w) < subset['Close']).mean() * 100
                     row[f"{w}hr"] = float(win_rate)
                     if win_rate >= 70: high_prob = True
                results_bear.append(row)
                
                if is_current and high_prob:
                     alert_msg = f"🚨 **HOURLY REVERSION ALERT** 🚨\nTicker: {TICKER}\nPrice: ${current_price:.2f}\nExtension: {current_ext:.2f}% ({label})\nProbability favors DROP."

        for threshold in np.arange(1.0, 10.0, 0.5):
            # Downside (Long Signal)
            subset = df[df['Ext_Pct'] <= -threshold]
            label = f"-{threshold:.1f}%"
            is_current = (current_ext <= -threshold) and (current_ext > -(threshold + 0.5))
            
            count = len(subset)
            if count >= 10:
                row = {"Condition": label, "Samples": str(count), "is_current": bool(is_current)}
                high_prob = False
                for w in windows:
                     win_rate = (subset['Close'].shift(-w) > subset['Close']).mean() * 100
                     row[f"{w}hr"] = float(win_rate)
                     if win_rate >= 70: high_prob = True
                results_bull.append(row)
                
                if is_current and high_prob:
                     alert_msg = f"🚨 **HOURLY REVERSION ALERT** 🚨\nTicker: {TICKER}\nPrice: ${current_price:.2f}\nExtension: {current_ext:.2f}% ({label})\nProbability favors BOUNCE."

        return results_bull, results_bear, alert_msg, current_ext

    def update_ui(self, bull_res, bear_res, current_ext):
        self.populate_table("#table_upside", bear_res)
        self.populate_table("#table_downside", bull_res)
        self.query_one("#status_lbl").update(f"📊 Current Ext: {current_ext:.2f}%")

if __name__ == "__main__":
    app = ReversionHourlyApp()
    app.run()
