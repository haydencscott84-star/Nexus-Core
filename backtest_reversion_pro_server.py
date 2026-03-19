import pandas as pd
import numpy as np
import asyncio
import os
import sys
import json
import requests
import time
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Button, Static, DataTable, Label
from rich.text import Text

try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except ImportError:
    # Fallback for UI testing if config missing
    TS_CLIENT_ID = ""
    TS_CLIENT_SECRET = ""
    TS_ACCOUNT_ID = ""

# --- CONFIGURATION ---
TICKER = "SPY"
YEARS_BACK = 10
SMA_PERIOD = 200
TARGET_WIN_RATE = 70.0
STATE_FILE = "reversion_pro_state.json"
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")

class ReversionProApp(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #1e1e1e;
    }
    Header {
        dock: top;
        background: #004400;
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
        background: #0055aa;
    }
    .box {
        height: auto;
        border: solid green;
        margin: 1 2; /* Increased side margin */
        padding: 1;
    }
    #live_ext_lbl {
        width: 1fr;
        content-align: center middle;
        background: #222;
        color: cyan;
        text-style: bold;
        border: solid #444;
        margin-right: 1;
    }
    Label {
        padding: 1 2; /* Added horizontal padding */
        background: #333;
        color: yellow;
        width: 100%;
        text-align: center;
        text-style: bold;
        margin-top: 1;
    }
    DataTable {
        height: auto;
        margin-bottom: 2; /* Space between tables */
    }
    """
    
    TITLE = f"Nexus Reversion PRO: {TICKER} (Daily)"
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with VerticalScroll():
            yield Static(f"PROTOCOL: Seeking >{TARGET_WIN_RATE}% Win Rate on 200 SMA Extensions", id="protocol_lbl")
            
            # Upside Table
            yield Label("🐻 BEARISH REVERSION (Price > 200 SMA)")
            yield DataTable(id="table_upside")
            
            # Downside Table
            yield Label("🐮 BULLISH REVERSION (Price < 200 SMA)")
            yield DataTable(id="table_downside")
            
            yield Static("", id="status_lbl")

        with Horizontal(id="controls"):
            yield Label("⏳ Waiting for Data...", id="live_ext_lbl")
            yield Button("REFRESH DATA", id="btn_refresh", variant="primary")

    def on_mount(self) -> None:
        self.init_tables()
        self.load_state()
        self.run_analysis()

    def init_tables(self):
        # COLUMNS
        cols = ["Condition", "Samples", "5 Days", "10 Days", "20 Days", "30 Days", "45 Days"]
        
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
        """Loads data from JSON to restore last state instantly."""
        if not os.path.exists(STATE_FILE):
            self.query_one("#status_lbl").update("⚠️ No previous state found. Please Refresh.")
            return

        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            
            self.populate_table("#table_upside", state.get("upside", []))
            self.populate_table("#table_downside", state.get("downside", []))
            
            last_upd = state.get("timestamp", "Unknown")
            curr_ext = state.get("current_ext", 0.0)
            
            self.query_one("#status_lbl").update(f"✅ State Loaded from: {last_upd}")
            self.query_one("#live_ext_lbl").update(f"📊 CURRENT EXTENSION: {curr_ext:.2f}%")
            self.title = f"Nexus Reversion PRO: {TICKER} (Last: {last_upd})"
            
        except Exception as e:
            self.query_one("#status_lbl").update(f"❌ Load Error: {e}")

    def populate_table(self, table_id, rows):
        table = self.query_one(table_id, DataTable)
        table.clear()
        
        for row in rows:
            # Row format: [label, count, rate5, rate10...]
            styled_row = [Text(str(row[0]), style="bold white"), Text(str(row[1]), justify="right")]
            
            # Win Rates
            for rate in row[2:]:
                val = float(rate)
                if val >= 80: style = "bold green"
                elif val >= 70: style = "green"
                elif val >= 60: style = "yellow"
                elif val < 50: style = "dim red"
                else: style = "dim white"
                
                txt = f"{val:.0f}%"
                styled_row.append(Text(txt, style=style))
            
            table.add_row(*styled_row)

    def run_analysis(self):
        """Runs the loop, fetches TS data, updates tables, saves state, alerts discord."""
        self.query_one("#status_lbl").update("⏳ Fetching 10 Years of Data from TradeStation...")
        
        # Run in worker to avoid blocking UI or crashing loop
        self.run_worker(self.async_analysis(), exclusive=True)

    def process_data(self, df, current_price):
        """Calculates probabilities and checks if CURRENT status matches high-conviction zone."""
        df['SMA_200'] = df['Close'].rolling(window=SMA_PERIOD).mean()
        df['Extension'] = ((df['Close'] - df['SMA_200']) / df['SMA_200']) * 100
        df.dropna(inplace=True)
        
        # Calculate Current Extension
        current_sma = df['SMA_200'].iloc[-1]
        current_ext = ((current_price - current_sma) / current_sma) * 100
        
        intervals = [5, 10, 20, 30, 45]
        results_bull = []
        results_bear = []
        
        # Alert Triggers
        alert_msg = ""
        
        # RANGE: -20% to +20% in 1% steps
        for i in range(-20, 21):
            if i == 0: continue
            
            # Bearish Reversion (Price > SMA) - Looking for price to DROP
            if i > 0:
                mask = (df['Extension'] >= i) & (df['Extension'] < i+1)
                match_txt = f"+{i}% to +{i+1}%"
                is_current = (current_ext >= i) and (current_ext < i+1)
            # Bullish Reversion (Price < SMA) - Looking for price to RISE
            else:
                mask = (df['Extension'] <= i) & (df['Extension'] > i-1)
                match_txt = f"{i}% to {i-1}%"
                is_current = (current_ext <= i) and (current_ext > i-1)

            total = len(df[mask])
            if total < 10: continue # Skip low sample size
            
            row = {"Condition": match_txt, "Samples": str(total), "is_current": is_current}
            high_prob_found = False

            for days in intervals:
                # Forward returns
                fwd_ret = df[mask]['Close'].shift(-days)
                
                if i > 0: # Bear Case: Win if Future < Current
                    wins = (fwd_ret < df[mask]['Close']).sum()
                else: # Bull Case: Win if Future > Current
                    wins = (fwd_ret > df[mask]['Close']).sum()
                    
                win_rate = (wins / total) * 100
                row[f"{days}d"] = win_rate
                
                if win_rate >= 70: high_prob_found = True
            
            if i > 0: results_bear.append(row)
            else: results_bull.append(row)
            
            # ALERT LOGIC: Only fire if IS CURRENT and PROB > 70%
            if is_current and high_prob_found:
                alert_msg = f"🚨 **REVERSION ALERT** 🚨\nTicker: {TICKER}\nCurrent Price: ${current_price:.2f}\nExtension: {current_ext:.2f}% (Zone: {match_txt})\n\n**Probability Favors Reversion:**"
                for days in intervals:
                    if row[f"{days}d"] >= 70:
                        alert_msg += f"\n- {days} Days: {row[f'{days}d']:.1f}% Win Rate"

        return results_bull, results_bear, alert_msg, current_ext

    def update_ui(self, bull_res, bear_res, current_ext):
        """Updates tables with improved visuals and highlights current zone."""
        dt_bear = self.query_one("#table_upside", DataTable); dt_bear.clear()
        dt_bull = self.query_one("#table_downside", DataTable); dt_bull.clear()
        
        def get_style(rate):
            if rate >= 80: return "bold green"
            if rate >= 70: return "green"
            if rate >= 60: return "yellow"
            if rate < 50: return "dim red"
            return "dim white"

        def pop_table(dt, res):
            for r in res:
                # Highlight ROW if current
                is_curr = r.get('is_current', False)
                base_style = "bold cyan" if is_curr else "white"
                
                cond_txt = f"> {r['Condition']}" if is_curr else r['Condition'] # Simple text indicator
                
                cells = [
                    Text(cond_txt, style=base_style),
                    Text(str(r["Samples"]), style="dim white"),
                    Text(f"{r['5d']:.0f}%", style=get_style(r['5d'])),
                    Text(f"{r['10d']:.0f}%", style=get_style(r['10d'])),
                    Text(f"{r['20d']:.0f}%", style=get_style(r['20d'])),
                    Text(f"{r['30d']:.0f}%", style=get_style(r['30d'])),
                    Text(f"{r['45d']:.0f}%", style=get_style(r['45d'])),
                ]
                dt.add_row(*cells)

        pop_table(dt_bear, bear_res)
        pop_table(dt_bull, bull_res)
        
        self.query_one("#live_ext_lbl").update(f"📊 CURRENT EXTENSION: {current_ext:.2f}%")
        self.query_one("#status_lbl").update("✅ Analysis Complete.")

    async def async_analysis(self):
        # 1. Fetch Data
        try:
            ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
            bars_needed = (252 * YEARS_BACK) + SMA_PERIOD + 50
            df = await ts.get_historical_data(TICKER, bars_needed, "Daily") 
            
            # Fetch Live Price for "Current" Check
            quote = ts.get_quote_snapshot(TICKER)
            try: current_price = float(quote.get('Last') or quote.get('Ask') or df['Close'].iloc[-1])
            except: current_price = float(df['Close'].iloc[-1])

            if df is not None and not df.empty:
                bull, bear, alert, curr_ext = self.process_data(df, current_price)
                self.call_from_thread(self.update_ui, bull, bear, curr_ext)
                
                # Save State
                state = {"bull": bull, "bear": bear, "last_updated": datetime.datetime.now().isoformat(), "current_ext": curr_ext}
                with open(STATE_FILE, "w") as f: json.dump(state, f)
                
                # Trigger Alert ONLY if message exists (meaning logic matched)
                if alert:
                    requests.post(DISCORD_WEBHOOK, json={"content": alert})
                    self.notify("Discord Alert Sent (Conditions Met)", severity="information")
                else:
                    self.notify(f"No Alert Triggered (Ext: {curr_ext:.2f}%)", severity="warning")

            else:
                self.notify("No Data Found", severity="error")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")
        finally:
            self.query_one("#btn_refresh").disabled = False

    def process_matrix(self, df, windows, is_upside):
        rows = [] # List of [label, count, r1, r2...]
        for threshold in range(2, 30):
            if is_upside:
                subset = df[df['Ext_Pct'] >= threshold]
                label = f"+{threshold}%"
            else:
                subset = df[df['Ext_Pct'] <= -threshold]
                label = f"-{threshold}%"
                
            count = len(subset)
            if count < 10: break
            
            row_data = [label, count]
            for w in windows[:-1]:
                if is_upside: win_rate = (subset[f'Ret_{w}d'] < 0).mean() * 100
                else: win_rate = (subset[f'Ret_{w}d'] > 0).mean() * 100
                row_data.append(round(win_rate, 1))
            
            rows.append(row_data)
        return rows

    def check_alerts(self, upside_rows, downside_rows):
        """Sends Discord alert if any active extension level has > 80% win rate."""
        alerts = []
        
        # Logic: Find current extension, match to row, check if setups are juicy
        # Actually, simpler: Just report the "Best Opportunities" (>80%) found in history
        # Better: Since this is backtest data, we should alert on WHAT THE CURRENT PRICE IS DOING.
        # But for now, user asked to "state reversion probabilities when criteria is met".
        
        # Let's find highest win rate rows
        for rows, kind in [(upside_rows, "BEARISH"), (downside_rows, "BULLISH")]:
            for r in rows:
                label = r[0]
                rates = r[2:]
                best_rate = max(rates)
                if best_rate >= 80:
                    alerts.append(f"**{kind}** {label}: Max Win Rate **{best_rate:.0f}%**")

        if alerts:
            # Limit to top 5 to avoid spam
            msg = f"**📊 Nexus Reversion Scan ({TICKER})**\nHigh Conviction Zones Found:\n" + "\n".join(alerts[:5])
            if len(alerts) > 5: msg += f"\n...and {len(alerts)-5} more."
            
            try:
                requests.post(DISCORD_WEBHOOK, json={"content": msg})
                self.query_one("#status_lbl").update(f"✅ Discord Alert Sent ({len(alerts)} zones)")
            except:
                pass

if __name__ == "__main__":
    app = ReversionProApp()
    app.run()
