from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, VerticalScroll
from textual.widgets import Header, Footer, Button, Static, DataTable, Label, Log
from rich.text import Text
import pandas as pd
import pandas_ta as ta
import asyncio
import datetime
import os
import requests
import json
import numpy as np

IMPORT_ERROR_MSG = None

# --- CONFIGURATION (Based on Optimization Winner) ---
TICKERS = ["SPY", "$SPX.X"]
HOURLY_PERIOD = 200
DAILY_PERIOD = 21

# Discord Webhook (From config or assumed global)
try:
    from nexus_config import DISCORD_WEBHOOK_URL as DISCORD_WEBHOOK, TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
    from tradestation_explorer import TradeStationManager
    HAS_TS = True
except ImportError as e:
    IMPORT_ERROR_MSG = str(e)
    HAS_TS = False
    DISCORD_WEBHOOK = ""
    TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID = "", "", ""


class MTFNexusApp(App):
    # ... CSS ...
    # ...
    # ... (skipping to on_mount)

    CSS = """
    Screen { layout: vertical; background: #0f172a; }
    Header { dock: top; background: #1e293b; color: white; height: 3; }
    #stats_bar { height: 3; background: #334155; align: center middle; }
    #stats_bar Label { color: #38bdf8; text-style: bold; margin: 0 2; }
    .legend { height: 1; background: #0f172a; align: center middle; }
    #lbl_legend { color: #94a3b8; text-style: italic; }
    
    #main_container { height: 1fr; }
    DataTable { height: 1fr; border: solid #475569; }
    
    #controls { height: 3; dock: bottom; background: #1e293b; align: center middle; }
    Button { background: #3b82f6; color: white; border: none; }
    Button:hover { background: #60a5fa; }
    
    Log { height: 10; border-top: solid white; background: #000; color: #0f0; }
    """
    
    TITLE = f"Nexus MTF Alert System ({', '.join(TICKERS)})"
    
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        with Horizontal(id="stats_bar"):
            yield Label("", id="lbl_price")
            yield Label("", id="lbl_hourly")
            yield Label("", id="lbl_slope")
            yield Label("", id="lbl_target")
            yield Label("", id="lbl_status")
        
        # LEGEND in Header/Sub-Header
        with Horizontal(id="legend_bar", classes="legend"):
            yield Label("Slope: >20°(🚀)  5-20°(✅)  -5/5°(Flat)  <-5°(🔻)", id="lbl_legend")

        with VerticalScroll(id="main_container"):
            yield DataTable(id="signal_table")
            yield Log(id="sys_log")

        with Horizontal(id="controls"):
            yield Button("FORCE REFRESH", id="btn_refresh")
            yield Button("TEST ALERT", id="btn_test")

    def on_mount(self) -> None:
        self.spy_price = 0.0 # Cache for SPY Price (used for SPX Multiplier)
        self.is_startup = True  # Initialize startup flag
        self.log_msg("🚀 System Startup. Connecting to TradeStation...")
        if not HAS_TS:
            try: self.log_msg(f"❌ CRITICAL IMPORT ERROR: {IMPORT_ERROR_MSG}")
            except: self.log_msg("❌ CRITICAL IMPORT ERROR: (Unknown)")
        
        self.init_table()
        # Start Loop (Every 15 minutes)
        self.set_interval(60 * 15, self.run_analysis) 
        # Run immediately
        self.run_worker(self.async_analysis(), exclusive=True)

    def init_table(self):
        dt = self.query_one("#signal_table", DataTable)
        dt.add_columns("Time", "Ticker", "Signal", "Price", "McMillan", "Rev Target", "Spreads", "Slope/Details")
        dt.cursor_type = "row"

    def calculate_mcmillan_bands(self, df, period=20):
        """
        Calculates McMillan Volatility Bands based on Realized Volatility.
        Returns modified DF with 'upper_2', 'upper_3', 'upper_4'.
        """
        try:
            # 1. Log Returns
            df['log_ret'] = np.log(df['Close'] / df['Close'].shift(1))
            
            # 2. Realized Volatility (Daily Sigma)
            df['sigma_daily'] = df['log_ret'].rolling(window=period).std()
            
            # 3. SMA 20 (Mean)
            df['sma_20'] = df['Close'].rolling(window=period).mean()
            
            # 4. Bands
            # Note: We focus on UPPER bands for Reversion (Shorting the Top)
            # Logic: Band = SMA * (1 + (N * Sigma))
            df['upper_2'] = df['sma_20'] * (1 + (2 * df['sigma_daily'])) 
            df['upper_3'] = df['sma_20'] * (1 + (3 * df['sigma_daily']))
            df['upper_4'] = df['sma_20'] * (1 + (4 * df['sigma_daily']))
            
            return df
        except Exception as e:
            self.log_msg(f"McMillan Calc Error: {e}")
            return df

    def log_msg(self, msg: str):
        log = self.query_one("#sys_log", Log)
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log.write_line(f"[{ts}] {msg}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_refresh":
            self.log_msg("Testing Manual Refresh...")
            self.manual_override = True # [FIX] Allow Bypass
            self.run_worker(self.async_analysis(), exclusive=True)
        elif event.button.id == "btn_test":
            self.send_discord_alert("TEST", "Manual Test Triggered", 0x3b82f6)

    def run_analysis(self):
        self.run_worker(self.async_analysis(), exclusive=True)

    def is_active_hours(self):
        import zoneinfo
        tz = zoneinfo.ZoneInfo("America/New_York")
        est_now = datetime.datetime.now(tz).replace(tzinfo=None)
        
        # 1. Weekend Check (Sat=5, Sun=6)
        if est_now.weekday() >= 5: return False
        
        # 2. Time Check (04:00 - 18:00)
        hour = est_now.hour
        # 4 <= hour < 18 (e.g. 17:59 is valid, 18:00 is not)
        if 4 <= hour < 18: return True
        
        return False

    async def async_analysis(self):
        # [RESTRICTION] 4AM-6PM M-F
        if not self.is_active_hours() and not self.query_one("#btn_refresh").has_focus: 
            # Allow manual refresh (button) to bypass, but loop should skip.
            # Actually, button uses this same func.
            # If manual button pressed, we should pass a flag?
            # For strict automation compliance:
            
            # Re-check: If called by 'on_button_pressed', we might want to allow it.
            # But simpler: Just log "Outside Hours" and skip if automated.
            
            if not getattr(self, "manual_override", False):
                self.log_msg("💤 Standard Hours Only (04:00-18:00 ET). Sleeping...")
                return
        
        self.manual_override = False # Reset flag
        
        self.log_msg("🔄 Fetching Market Data...")
        if not HAS_TS:
            self.log_msg("❌ ERROR: TradeStation lib missing.")
            return

        # Instantiate Manager Once
        ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
        
        # Loop through all configured tickers
        mtf_payloads = {}
        for ticker in TICKERS:
            p_data = await self.analyze_ticker(ts, ticker)
            if p_data:
                mtf_payloads[ticker] = p_data
                
        if mtf_payloads:
            try:
                from supabase_bridge import upload_json_to_supabase
                await upload_json_to_supabase("nexus_profile", mtf_payloads, id_value="mtf_latest")
                self.log_msg(f"☁️ Supabase MTF Data Sync OK")
            except Exception as e:
                self.log_msg(f"❌ Supabase Upload Failed: {e}")
            
            
        # Clear startup flag after loop
        if self.is_startup: self.is_startup = False

    async def analyze_ticker(self, ts, ticker):
        """Analyzes a single ticker and updates the TUI."""
        try:
             # Fetch Hourly (Need coverage for 200 SMA)
            h_bars = ts.get_historical_data(ticker, unit="Minute", interval="60", bars_back="3000")
            # Fetch Daily (Need coverage for 21 SMA)
            d_bars = ts.get_historical_data(ticker, unit="Daily", interval="1", bars_back="500")

            if not h_bars or not d_bars:
                self.log_msg(f"⚠️ API No Data for {ticker}.")
                return

            # Process DF
            h_df = self.process_bars(h_bars)
            d_df = self.process_bars(d_bars)
            
            # --- STRATEGY LOGIC ---
            # 1. Indicators
            h_df.ta.sma(length=HOURLY_PERIOD, append=True) # SMA_200
            d_df.ta.sma(length=DAILY_PERIOD, append=True)  # SMA_21

            # --- EXTRACT PRICES & MULTIPLIER ---
            curr_price = h_df['Close'].iloc[-1]
            if ticker == "SPY": self.spy_price = curr_price # Update Cache

            # --- MULTIPLIER LOGIC (SPX -> SPY Equivalent) ---
            multiplier = 1.0
            price_display = f"${curr_price:.2f}"
            
            if ticker == "$SPX.X" and self.spy_price > 0:
                multiplier = curr_price / self.spy_price
                eq_price = curr_price / multiplier 
                price_display = f"${curr_price:.2f} [Eq: ${eq_price:.2f}]"
            
            # Helper for conversion
            def to_eq(val): 
                if multiplier == 1.0: return ""
                return f" ({val/multiplier:.2f})"

            # --- PREP COMPARISON LOGIC ---
            d_df['ATR'] = d_df.ta.atr(length=14)
            
            # NORMALIZED SLOPE LOGIC
            # If SPX, we scale the SMA down by the multiplier so the 'degrees' match SPY's scale.
            sma_series = d_df[f"SMA_{DAILY_PERIOD}"]
            if multiplier != 1.0:
                sma_series = sma_series / multiplier

            d_df['SMA_Slope'] = np.rad2deg(np.arctan(sma_series.diff(3) / 3))
            
            h_df.ta.sma(length=8, append=True)
            h_df.ta.sma(length=21, append=True)

            # --- MCMILLAN INTEGRATION ---
            d_df = self.calculate_mcmillan_bands(d_df)
            curr_daily = d_df.iloc[-1]
            
            # Init Defaults
            mc_sma = 0.0; mc_u3 = 0.0; mc_u4 = 0.0
            mc_status = "WAIT"; mc_target_str = "-"
            
            try:
                mc_sma = curr_daily['sma_20']
                mc_u3 = curr_daily['upper_3']
                mc_u4 = curr_daily['upper_4']
                
                recent_window = d_df.iloc[-6:-1]
                setup_triggered = (recent_window['Close'] > recent_window['upper_4']).any()
                
                trigger_fired = curr_daily['Close'] < mc_u3
                
                # Logic States
                mc_status = "ARMED (Scanning)"
                mc_color = "cyan"
                mc_target_str = f"U4: ${mc_u4:.2f}{to_eq(mc_u4)}" 
                
                if setup_triggered and trigger_fired:
                    mc_status = "🚨 EXECUTE REVT"
                    mc_color = "red"
                    mc_target_str = f"TGT: ${curr_daily['upper_2']:.2f}{to_eq(curr_daily['upper_2'])}"
                    
                    alert_msg = (f"**🚨 MCMILLAN REVERSAL SIGNAL**\n"
                                 f"Ticker: {ticker}\n"
                                 f"Price: {price_display}\n"
                                 f"Condition: Exhaustion (>4σ) -> Reversion (<3σ)\n"
                                 f"Target 1: ${curr_daily['upper_2']:.2f}{to_eq(curr_daily['upper_2'])}\n"
                                 f"Target 2: ${mc_sma:.2f}{to_eq(mc_sma)} (Mean)")
                    # Unique Key per Ticker
                    self.check_and_alert(f"{ticker}_MCMILLAN_REV", alert_msg, 0xff0000)
                    
                elif curr_daily['Close'] > mc_u4:
                    mc_status = "⚠️ EXTREME (>4σ)"
                    mc_color = "yellow"
                    mc_target_str = "WAIT FOR SNAP"
                elif curr_daily['Close'] > mc_u3:
                    mc_status = "WATCH (>3σ)"
                    mc_color = "orange"
                    mc_target_str = f"Snap: <${mc_u3:.2f}{to_eq(mc_u3)}"
                    
                mc_display = f"[{mc_color}]{mc_status}[/]"
                
            except Exception as e:
                self.log_msg(f"McMillan Logic Fail for {ticker}: {e}")
                mc_display = "ERR"
                mc_target_str = "-"

            d_sma_col = f"SMA_{DAILY_PERIOD}"
            h_sma_col = f"SMA_{HOURLY_PERIOD}"
            
            d_sma_aligned = d_df[d_sma_col].shift(1).reindex(h_df.index).ffill()
            h_sma = h_df[h_sma_col]
            
            curr_h_sma = h_sma.iloc[-1]
            curr_d_sma = d_sma_aligned.iloc[-1]
            
            curr_atr = d_df['ATR'].iloc[-1]
            curr_slope_deg = d_df['SMA_Slope'].iloc[-1]
            
            h_8 = h_df['SMA_8'].iloc[-1]
            h_21 = h_df['SMA_21'].iloc[-1]
            hourly_drag = h_8 < h_21

            # Downside Pulse Logic
            c_1 = h_df['Close'].iloc[-1]
            c_2 = h_df['Close'].iloc[-2]
            h8_1 = h_df['SMA_8'].iloc[-1]
            h8_2 = h_df['SMA_8'].iloc[-2]
            h21_1 = h_df['SMA_21'].iloc[-1]
            h21_2 = h_df['SMA_21'].iloc[-2]

            downside_pulse = (c_1 < h8_1 and c_1 < h21_1) and (c_2 < h8_2 and c_2 < h21_2)

            is_bullish = (curr_price > curr_h_sma) and (curr_price > curr_d_sma)
            is_bearish = (curr_price < curr_h_sma)
            
            status = "NEUTRAL"
            color = "white"
            
            if is_bullish:
                status = "🟢 BULLISH TREND"
                color = "green"
            elif is_bearish:
                status = "🔴 BEARISH / CASH"
                color = "red"

            # --- C. TARGET GENERATION ---
            if is_bullish:
                optimal_put = curr_d_sma - (1.0 * curr_atr)
                optimal_call = curr_price + (1.0 * curr_atr)
                
                if downside_pulse:
                     put_label = f"Put: ${optimal_put:.2f}{to_eq(optimal_put)} (⚠️ Caution)"
                     put_context = "⚠️ CAUTION: Hourly Downside Pulse"
                else:
                     put_label = f"Put: ${optimal_put:.2f}{to_eq(optimal_put)} (✅)"
                     put_context = "✅ PUTS FAVORED"

                if hourly_drag:
                    call_context = "⚠️->✅ (Hourly Drag)" 
                    call_label = f"Call: ${optimal_call:.2f}{to_eq(optimal_call)} (Viable Rev)"
                else:
                    call_context = "⚠️ High Risk"
                    call_label = f"Call: ${optimal_call:.2f}{to_eq(optimal_call)} (⚠️)"

                side_context = (f"BULLISH MARKET ({ticker})\n"
                                f"{put_context} (Short: ${optimal_put:.2f}{to_eq(optimal_put)})\n"
                                f"{call_context} (Short: ${optimal_call:.2f}{to_eq(optimal_call)})")
                
                short_leg_display = f"{put_label} | {call_label}"

            elif is_bearish:
                optimal_put = curr_price - (1.0 * curr_atr)
                optimal_call = curr_d_sma + (1.0 * curr_atr)
                
                side_context = (f"BEARISH MARKET ({ticker})\n"
                                f"✅ CALLS FAVORED (Short: ${optimal_call:.2f}{to_eq(optimal_call)})\n"
                                f"⚠️ PUTS RISKY (Short: ${optimal_put:.2f}{to_eq(optimal_put)})")
                
                short_leg_display = f"Call: ${optimal_call:.2f}{to_eq(optimal_call)} (✅) | Put: ${optimal_put:.2f}{to_eq(optimal_put)} (⚠️)"

            else:
                optimal_put = curr_price - curr_atr
                optimal_call = curr_price + curr_atr
                side_context = "NEUTRAL / CHOP"
                short_leg_display = f"Range: ${optimal_put:.2f}{to_eq(optimal_put)} - ${optimal_call:.2f}{to_eq(optimal_call)}"

            # Only update Header Labels if it's the Primary Ticker (Optional: or show last?)
            if ticker == "SPY":
                self.query_one("#lbl_price").update(f"SPY: ${curr_price:.2f}")
                self.query_one("#lbl_hourly").update(f"D{DAILY_PERIOD}: ${curr_d_sma:.2f}")
                self.query_one("#lbl_slope").update(f"Slope: {curr_slope_deg:.1f}°")
                self.query_one("#lbl_target").update(short_leg_display)
                self.query_one("#lbl_status").update(f"[{color}]{status}[/]")
            
            self.log_msg(f"✅ Analysis Done for {ticker}. Algo State: {status}")
            
            spread_str = short_leg_display.replace("Put:", "PCS:").replace("Call:", "CCS:")
            
            payload_data = {
                "ticker": ticker,
                "price": curr_price,
                "price_str": price_display,
                "status": status,
                "color": color,
                "mc_display": mc_display,
                "mc_target": mc_target_str,
                "spreads": spread_str,
                "slope": round(float(curr_slope_deg), 2),
                "timestamp": datetime.datetime.now().isoformat(),
                "daily_sma": round(float(curr_d_sma), 2)
            }

            # Record in Table
            dt = self.query_one("#signal_table", DataTable)
            row = [
                datetime.datetime.now().strftime("%H:%M"),
                ticker, 
                status,
                price_display, # [UPDATED]
                mc_display,  
                mc_target_str, # [UPDATED]
                spread_str,    # [UPDATED]
                f"Slope: {curr_slope_deg:.1f}°" 
            ]
            dt.add_row(*row)
            
            # --- SIGNAL GENERATION ---
            floor_is_solid = curr_slope_deg > -3 
            
            # McMillan Context for Trend Alerts
            mc_alert_context = (f"\n\n**McMillan Strategy**\n"
                                f"Status: {mc_status}\n"
                                f"Target: {mc_target_str}\n"
                                f"Mean: ${mc_sma:.2f}{to_eq(mc_sma)}")

            if is_bullish and floor_is_solid:
                 msg = (f"**🟢 SIGNAL: PUT SPREADS ({ticker})**\n"
                        f"Price: {price_display}\n"
                        f"Daily Slope: {curr_slope_deg:.1f}°\n"
                        f"{side_context}"
                        f"{mc_alert_context}")
                 self.check_and_alert(f"{ticker}_MTF_ENTRY", msg, 0x22c55e)

            elif is_bearish:
                 msg = (f"**🔴 SIGNAL: CALL SPREADS ({ticker})**\n"
                        f"Price: {price_display}\n"
                        f"Daily Slope: {curr_slope_deg:.1f}°\n"
                        f"{side_context}"
                        f"{mc_alert_context}")
                 self.check_and_alert(f"{ticker}_MTF_EXIT", msg, 0xef4444)
            
            return payload_data
            
        except Exception as e:
            self.log_msg(f"❌ Error analyzing {ticker}: {e}")
            return None

    def check_and_alert(self, state_key, msg, color):
        """Sends alert only if 1 hour passed since last same-type alert."""
        state_file = "mtf_state.json"
        now = datetime.datetime.now().timestamp()
        
        try:
            if os.path.exists(state_file):
                with open(state_file, 'r') as f: state = json.load(f)
            else: state = {}
            
            last_time = state.get(state_key, 0)
            
            # Throttle: 1 Hour (3600s), UNLESS it's startup
            if (now - last_time < 3600) and (not self.is_startup): 
                return
            
            # Send to Discord
            payload = {
                "username": "Nexus MTF",
                "embeds": [{
                    "title": f"MTF STATUS: {state_key}",
                    "description": msg,
                    "color": color,
                    "footer": {"text": "Nexus V2.5 • Daily/Hourly Logic"}
                }]
            }
            requests.post(DISCORD_WEBHOOK, json=payload)
            
            # Update State
            state[state_key] = now
            with open(state_file, 'w') as f: json.dump(state, f)
            
            self.log_msg(f"✅ ALERT SENT: {state_key}")
            
        except Exception as e:
            self.log_msg(f"❌ Alert Fail: {e}")

    def send_discord_alert(self, title, description, color):
        if not DISCORD_WEBHOOK: return
        payload = {
            "embeds": [{
                "title": title, "description": description, "color": color,
                "timestamp": datetime.datetime.now().isoformat()
            }]
        }
        try: requests.post(DISCORD_WEBHOOK, json=payload)
        except: pass

    def process_bars(self, bars):
        df = pd.DataFrame(bars)
        date_col = 'TimeStamp' if 'TimeStamp' in df.columns else 'Timestamp'
        df['Close'] = pd.to_numeric(df['Close'])
        df['High'] = pd.to_numeric(df['High'])
        df['Low'] = pd.to_numeric(df['Low'])
        df['Open'] = pd.to_numeric(df['Open'])
        df.index = pd.to_datetime(df[date_col])
        return df.sort_index()

if __name__ == "__main__":
    app = MTFNexusApp()
    app.run()
