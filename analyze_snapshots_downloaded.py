 
# FILE: analyze_snapshots.py
import nexus_lock
nexus_lock.enforce_singleton()
import zmq
import zmq.asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import json
import asyncio
import signal
import glob
import time # Ensure time is available for lazy loading if needed
import requests # Added for data fetching
import shutil # Added for archiving


# Direct Feed Fallback
try:
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
    from tradestation_explorer import TradeStationManager
except ImportError:
    pass

# Add this path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Select, Label, Button, TabbedContent, TabPane, Log, ProgressBar
from textual.containers import Container, Horizontal, Vertical, Grid
from rich.text import Text
import re
from rich.panel import Panel
from rich.align import Align
from textual import on
from textual.reactive import reactive

# --- API FALLBACK IMPORTS ---
try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID, DISCORD_WEBHOOK_URL
    # Access API Keys from nexus_config or env if available, else hardcode fallback (safe for local)
    UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
    ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
except ImportError:
    TradeStationManager = None
    TS_CLIENT_ID = None
    DISCORD_WEBHOOK_URL = None
    UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")
    ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

# --- GREEKS ENRICHMENT ---
try:
    from enrich_with_greeks import enrich_traps_with_greeks
except ImportError:
    def enrich_traps_with_greeks(df): return df

# [FIX] Helper for formatting - Global Scope to avoid UnboundLocalError
def fmt_oi_delta(val):
    abs_val = abs(val)
    if abs_val >= 1_000_000: return f"{val/1_000_000:+.1f}M"
    if abs_val >= 1_000: return f"{val/1_000:+.1f}K"
    return f"{val:+.1f}"

def fmt_notional(val, show_plus=True):
    if pd.isna(val): return "-"
    abs_val = abs(val)
    if abs_val >= 1_000_000:
        s = f"{val/1_000_000:.1f}M"
    elif abs_val >= 1_000:
        s = f"{val/1_000:.1f}K"
    else:
        s = f"{val:.1f}"
    
    if show_plus and val > 0:
        return f"+{s}"
    return s

# --- TIMEZONE SETUP ---
try:
    import pytz
    ET_TZ = pytz.timezone('US/Eastern')
except ImportError:
    ET_TZ = None

def get_today_date():
    """Get current date in US/Eastern to prevent premature expiry on UTC servers."""
    if ET_TZ: return datetime.now(ET_TZ).date()
    return (datetime.utcnow() - timedelta(hours=5)).date()

def get_now_str():
    if ET_TZ: return datetime.now(ET_TZ).strftime('%H:%M:%S')
    return (datetime.utcnow() - timedelta(hours=5)).strftime('%H:%M:%S')

# --- CONFIG ---
DATA_SOURCES = {
    'sweeps': 'snapshots_sweeps', 
    'spy': 'snapshots_spy',       
    'spx': 'snapshots'            
}

# --- ENGINE ---
def prune_archived_data(days_keep=30):
    print(f"🧹 STARTING PRUNE: Keeping {days_keep} days.")
    base_path = os.getcwd()
    print(f"   Base Path: {base_path}")
    cutoff_date = (datetime.now() - timedelta(days=days_keep)).date()
    
    for source_name, folder in DATA_SOURCES.items():
        full_path = os.path.join(base_path, folder)
        archive_path = os.path.join(full_path, "archive")
        
        if not os.path.exists(full_path):
            print(f"   Skipping {source_name}: Path {full_path} not found.")
            continue
            
        try:
            os.makedirs(archive_path, exist_ok=True)
            print(f"   Checking {source_name} ({full_path})...")
        except Exception as e:
            print(f"   Error creating archive dir: {e}")
            continue
        
        all_files = glob.glob(os.path.join(full_path, "*.csv"))
        print(f"   Found {len(all_files)} CSV files.")
        files_moved = 0
        
        for f in all_files:
            try:
                filename = os.path.basename(f)
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if file_date < cutoff_date:
                        # Move to archive
                        shutil.move(f, os.path.join(archive_path, filename))
                        files_moved += 1
            except Exception as e:
                print(f"   Error archiving {f}: {e}")
                
        if files_moved > 0:
            print(f"🧹 [Maintenance] Archived {files_moved} old files from {source_name}")
        else:
            print(f"   No files to archive in {source_name}")

def load_unified_data(days_back, log_func=None):
    # Perform maintenance first
    # [OPTIMIZATION] Moved to background execution to prevent freeze
    # try: prune_archived_data(days_keep=30)
    # except: pass

    base_path = os.getcwd()
    master_dfs = []
    # Fix: Ensure cutoff is at midnight to capture full days
    cutoff = (datetime.now() - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    files_loaded = 0
    
    for source_name, folder in DATA_SOURCES.items():
        full_path = os.path.join(base_path, folder)
        all_files = sorted(glob.glob(os.path.join(full_path, "*.csv")))
        latest_files_map = {}
        
        # Get latest file per day
        for f in all_files:
            try:
                filename = os.path.basename(f)
                # Fix: Use Regex to find date YYYY-MM-DD
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    date_str = match.group(1)
                    latest_files_map[date_str] = f
            except: pass
        unique_files = list(latest_files_map.values())
        
        for f in unique_files:
            try:
                filename = os.path.basename(f)
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if not match: continue
                
                dt_str = match.group(1)
                file_date = datetime.strptime(dt_str, "%Y-%m-%d")
                if files_loaded < 3:
                    print(f"DEBUG: Loading {f}...")
                    try:
                        df_peek = pd.read_csv(f, nrows=1)
                        print(f"DEBUG: Columns in {os.path.basename(f)}: {list(df_peek.columns)}")
                    except: pass
                
                if file_date >= cutoff:
                    if log_func: log_func(f"  -> Loading: {os.path.basename(f)} ({file_date})")
                    df = pd.read_csv(f)
                    if df.empty: continue
                    files_loaded += 1
                    
                    # Standardize Columns
                    std_df = pd.DataFrame(index=df.index) # Fix: Initialize with index to allow scalar broadcasting
                    std_df['date'] = file_date
                    
                    # Helper for Delta Loading
                    def get_delta_col(cols):
                        lower_cols = cols.str.lower()
                        if 'delta' in lower_cols: return cols[lower_cols.get_loc('delta')]
                        if 'greeks_delta' in lower_cols: return cols[lower_cols.get_loc('greeks_delta')]
                        if 'imp_delta' in lower_cols: return cols[lower_cols.get_loc('imp_delta')]
                        if 'd' in lower_cols: return cols[lower_cols.get_loc('d')]
                        return None

                    if source_name == 'sweeps':
                        # Map columns based on inspection: 
                        # ['ticker', 'parsed_expiry', 'parsed_dte', 'parsed_strike', 'parsed_type', 'sentiment_str', 'total_premium', 'priority_score', 'priority_notes', 'price', 'total_size', 'open_interest']
                        if 'total_premium' in df.columns:
                            std_df['ticker'] = df['ticker']
                            std_df['strike'] = pd.to_numeric(df['parsed_strike'], errors='coerce')
                            std_df['type'] = df['parsed_type']
                            std_df['premium'] = pd.to_numeric(df['total_premium'], errors='coerce').fillna(0)
                            std_df['vol'] = pd.to_numeric(df['total_size'], errors='coerce').fillna(0)
                            std_df['oi'] = pd.to_numeric(df['open_interest'], errors='coerce').fillna(0)
                            
                            d_col = get_delta_col(df.columns)
                            if d_col: std_df['delta'] = pd.to_numeric(df[d_col], errors='coerce').fillna(0)
                            else: std_df['delta'] = 0.0
                            

                            if 'gamma' in df.columns: std_df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0)
                            else: std_df['gamma'] = 0.0
                            
                            if 'vega' in df.columns: std_df['vega'] = pd.to_numeric(df['vega'], errors='coerce').fillna(0)
                            else: std_df['vega'] = 0.0

                            if 'theta' in df.columns: std_df['theta'] = pd.to_numeric(df['theta'], errors='coerce').fillna(0)
                            else: std_df['theta'] = 0.0
                            
                            std_df['expiry'] = df['parsed_expiry']
                            std_df['dte'] = pd.to_numeric(df['parsed_dte'], errors='coerce').fillna(0)

                            std_df['is_bull'] = ((df['sentiment_str']=='BUY') & (df['parsed_type']=='CALL')) | \
                                                ((df['sentiment_str']=='SELL') & (df['parsed_type']=='PUT'))
                    elif source_name in ['spy', 'spx']:
                        # Map columns based on inspection:
                        # SPY: ['symbol', 'exp', 'dte', 'stk', 'type', 'prem', 'vol', 'oi', 'voi_ratio', 'edge', 'conf', 'win']
                        # SPX: ['sym', 'exp', 'dte', 'stk', 'type', 'side_tag', 'prem', 'vol', 'oi', 'edge', 'conf', 'win']
                        std_df['ticker'] = source_name.upper()
                        std_df['strike'] = pd.to_numeric(df['stk'], errors='coerce')

                        # Handle Type (SPY has 'PUT'/'CALL', SPX has 'C'/'P'?)
                        # Inspection showed SPY: 'PUT', SPX: 'C'. Need to normalize.
                        if 'type' in df.columns:
                            std_df['type'] = df['type'].astype(str).str.upper().apply(lambda x: 'CALL' if x.startswith('C') else ('PUT' if x.startswith('P') else x))
                        else:
                            std_df['type'] = 'UNKNOWN'
                            
                        std_df['premium'] = pd.to_numeric(df['prem'], errors='coerce').fillna(0)
                        std_df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)
                        std_df['oi'] = pd.to_numeric(df['oi'], errors='coerce').fillna(0)
                        
                        d_col = get_delta_col(df.columns)
                        if d_col: std_df['delta'] = pd.to_numeric(df[d_col], errors='coerce').fillna(0)
                        else: std_df['delta'] = 0.0
                        
                        if 'gamma' in df.columns: std_df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0)
                        else: std_df['gamma'] = 0.0

                        if 'vega' in df.columns: std_df['vega'] = pd.to_numeric(df['vega'], errors='coerce').fillna(0)
                        else: std_df['vega'] = 0.0

                        if 'theta' in df.columns: std_df['theta'] = pd.to_numeric(df['theta'], errors='coerce').fillna(0)
                        else: std_df['theta'] = 0.0

                        if 'vega' in df.columns: std_df['vega'] = pd.to_numeric(df['vega'], errors='coerce').fillna(0)
                        else: std_df['vega'] = 0.0

                        if 'theta' in df.columns: std_df['theta'] = pd.to_numeric(df['theta'], errors='coerce').fillna(0)
                        else: std_df['theta'] = 0.0
                        
                        std_df['expiry'] = df['exp']
                        std_df['dte'] = pd.to_numeric(df['dte'], errors='coerce').fillna(0)
                        
                        if 'conf' in df.columns: std_df['is_bull'] = df['conf'].astype(str).str.contains("BULL")
                        else: std_df['is_bull'] = False
                        
                        # Capture Spot Price if available
                        if 'underlying_price' in df.columns:
                            std_df['underlying_price'] = pd.to_numeric(df['underlying_price'], errors='coerce').fillna(0)
                        else:
                            std_df['underlying_price'] = 0.0
                            
                    master_dfs.append(std_df)
            except: pass

    if log_func: log_func(f"Loaded {files_loaded} snapshot files across {len(DATA_SOURCES)} sources.")

    if not master_dfs: return pd.DataFrame()
    master = pd.concat(master_dfs, ignore_index=True)
    
    # --- DIAGNOSTICS ---
    unique_dates = sorted(list(set([d.strftime('%Y-%m-%d') for d in master['date'] if pd.notnull(d)])))
    if log_func:
        log_func(f"📊 DATA AUDIT: Found {len(unique_dates)} days of history.")
        log_func(f"📅 DATES LOADED: {unique_dates}")
    else:
        print(f"📊 DATA AUDIT: Found {len(unique_dates)} days of history.")
        print(f"📅 DATES LOADED: {unique_dates}")
        
    if len(unique_dates) < 5:
        msg = f"⚠️ WARNING: Less than 5 days of data ({len(unique_dates)} days). Trend analysis will be incomplete."
        if log_func: log_func(msg)
        else: print(msg)
    # -------------------
    
    # --- DEDUPLICATION ---
    # Drop duplicates based on key trade identifiers to prevent double-counting
    # from overlapping script runs or v1/v2 redundancy.
    before_len = len(master)
    dedup_cols = ['ticker', 'strike', 'expiry', 'type', 'premium', 'vol', 'date']
    # If 'executed_at' or 'time' exists, include it for precision
    if 'executed_at' in master.columns: dedup_cols.append('executed_at')
    
    # Safe dedup: Only use columns that exist
    actual_dedup_cols = [c for c in dedup_cols if c in master.columns]
    if actual_dedup_cols:
        master.drop_duplicates(subset=actual_dedup_cols, inplace=True)
        
    if log_func: log_func(f"Deduplication: {before_len} -> {len(master)} rows (Removed {before_len - len(master)})")
    # ---------------------
    
    # --- EXPIRED CONTRACT PURGE (REMOVED GLOBAL) ---
    # We want to keep expired contracts for HISTORICAL analysis (Heatmap).
    # We will filter them out locally for the Kill Box (Active Traps).
    # -----------------------------------------------

    master['strike'] = pd.to_numeric(master['strike'], errors='coerce').fillna(0)
    
    def auto_correct_ticker(row):
        if row['strike'] > 2000: return "SPX"
        if row['strike'] < 1500: return "SPY"
        return row['ticker']
        
    master['ticker'] = master.apply(auto_correct_ticker, axis=1)
    master['norm_strike'] = master.apply(lambda x: x['strike']/10 if x['ticker'] == "SPX" else x['strike'], axis=1)
    
    return master

def analyze_persistence(df):
    """
    Analyzes Position Persistence: OI Delta, Ghost, Fortress, VWAP.
    """
    if df.empty: return pd.DataFrame()
    
    # Group by Ticker, Strike, Expiry, Date
    # We want to aggregate metrics per day per contract
    daily_stats = df.groupby(['ticker', 'strike', 'expiry', 'date']).agg({
        'oi': 'max', # OI is usually a snapshot, max is safe for end of day
        'vol': 'max', # Fix: Use MAX instead of SUM to prevent double counting matching snapshots
        'premium': 'max', # Fix: Use MAX instead of SUM
        'is_bull': lambda x: (x == True).sum() / len(x) if len(x) > 0 else 0 # Bull Ratio
    }).reset_index()
    
    daily_stats.sort_values(['ticker', 'strike', 'expiry', 'date'], inplace=True)
    
    # Calculate OI Delta
    daily_stats['prev_oi'] = daily_stats.groupby(['ticker', 'strike', 'expiry'])['oi'].shift(1)
    daily_stats['oi_delta'] = daily_stats['oi'] - daily_stats['prev_oi']
    daily_stats['oi_delta'] = daily_stats['oi_delta'].fillna(0)
    
    # VWAP Calculation (Cumulative for the period loaded)
    # Fix: VWAP = Total Premium / Total Volume (Weighted Average)
    daily_stats['avg_price'] = daily_stats['premium'] / daily_stats['vol'].replace(0, 1)
    
    # Ghost Filter: High Vol but Negative OI Delta
    # "Fresh Flow" usually means Vol > OI.
    # Ghost: Massive Fresh Flow on Day 1, but OI decreased on Day 2?
    # Simplified Ghost: High Vol today, but OI Delta is Negative or Zero.
    daily_stats['is_ghost'] = (daily_stats['vol'] > 1000) & (daily_stats['oi_delta'] <= 0)
    
    # Fortress Detector: OI Increased for 3 consecutive days
    # We need a rolling window check.
    daily_stats['oi_inc'] = daily_stats['oi_delta'] > 0
    # Fix: Drop all grouping levels (ticker, strike, expiry) to align with original index
    daily_stats['fortress_count'] = daily_stats.groupby(['ticker', 'strike', 'expiry'])['oi_inc'].rolling(3).sum().reset_index(level=[0,1,2], drop=True)
    daily_stats['is_fortress'] = daily_stats['fortress_count'] >= 3
    
    return daily_stats

def fmt_num(x):
    if abs(x) >= 1e9: return f"${x/1e9:.1f}B"
    if abs(x) >= 1e6: return f"${x/1e6:.1f}M"
    if abs(x) >= 1e3: return f"${x/1e3:.0f}K"
    return f"${x:.0f}"

def fmt_oi_delta(val):
    if abs(val) >= 1e6: return f"{val/1e6:+.1f}M"
    if abs(val) >= 1e3: return f"{val/1e3:+.0f}K"
    return f"{val:+.0f}"

def generate_expiry_narrative(df, days_back=10):
    """
    Generates a narrative string for the top expirations.
    """
    if df.empty: return "No data available."
    
    # Filter for last N days
    cutoff = df['date'].max() - timedelta(days=days_back)
    recent_df = df[df['date'] >= cutoff]
    
    if recent_df.empty: return "No recent data for narrative."
    
    # Group by Expiry
    exp_stats = recent_df.groupby('expiry').apply(
        lambda x: pd.Series({
            'net_flow': x[x['is_bull']]['premium'].sum() - x[~x['is_bull']]['premium'].sum(),
            'total_vol': x['premium'].sum(),
            'bull_vol': x[x['is_bull']]['premium'].sum(),
            'bear_vol': x[~x['is_bull']]['premium'].sum()
        })
    ).reset_index()
    
    exp_stats.sort_values('total_vol', ascending=False, inplace=True)
    
    if exp_stats.empty: return "No active expirations."
    
    narratives = []
    for i, row in exp_stats.head(3).iterrows():
        expiry = row['expiry']
        net_flow = row['net_flow']
        flow_type = "Bullish" if net_flow > 0 else "Bearish"
        
        narratives.append(f"Over the last {days_back} days, ${abs(net_flow):,.0f} of {flow_type} flow has rotated into the {expiry} Expiry.")
        
    return "\n".join(narratives)

# --- APP ---
class StrategicHUD(App):
    CSS = """
    Screen {
        layout: vertical;
        background: #0f111a;
    }
    DataTable {
        height: auto;
        min-height: 10;
        scrollbar-size: 1 1;
        scrollbar-color: #444444;
        scrollbar-corner-color: #333333;
    }
    #header-container { height: 6; dock: top; background: $surface-darken-1; border-bottom: solid $primary; padding: 0 1; }
    /* #heatmap-container { height: 1fr; border-bottom: solid $secondary; } REMOVED */
    #kill-split { layout: vertical; height: 1fr; background: $surface; }
    #dt_kill_spx { width: 100%; height: 50%; border-bottom: solid $secondary; }
    #dt_kill_spy { width: 100%; height: 50%; }
    
    DataTable { height: 1fr; } 
    .dt-cell { min-width: 10; } /* Force width logic */
    #dt_market_struct { height: 1fr; }
    
    .lbl { text-style: bold; color: $text-muted; }
    .val { text-style: bold; color: $text; margin-right: 2; }
    
    DataTable { height: 1fr; }
    #narrative-box { height: 3; background: $surface-darken-2; border: solid $secondary; padding: 0 1; color: $text; overflow-y: scroll; }
    
    #regime-lbl { color: $accent; text-style: bold; }
    
    #log-container { dock: bottom; height: 20%; border-top: solid $secondary; background: $surface; }
    Log { height: 100%; overflow-y: scroll; }
    """
    
    current_df = pd.DataFrame()
    daily_stats = pd.DataFrame()
    
    sentiment_score = reactive(50.0) # 0 = Bear, 100 = Bull
    market_regime = reactive("NEUTRAL")
    divergence_alert = reactive(None) # None, "BEAR", "BULL"
    last_spot_price = reactive(0.0)

    def compose(self) -> ComposeResult:
        with Container(id="header-container"):
            with Horizontal():
                yield Label("Strategic Narrative:", classes="lbl")
                yield Static("Loading Narrative...", id="narrative-box")
            with Horizontal():
                yield Label("Market Regime:", classes="lbl")
                yield Label("ANALYZING...", id="regime-lbl", classes="val")
                yield Label("Divergence:", classes="lbl")
                yield Label("NONE", id="div-lbl", classes="val")
                yield Label("Last Updated:", classes="lbl")
                yield Label("-", id="last-updated-lbl", classes="val")
                yield Button("REFRESH", id="btn_refresh", variant="primary", classes="val")
        
        # Heatmap Removed
        with Container(id="kill-split"):
             with TabbedContent():
                 with TabPane("Whale/Retail Traps", id="tab_traps"):
                     with Vertical():
                         yield DataTable(id="dt_kill_spx")
                         yield DataTable(id="dt_kill_spy")
                 with TabPane("Market Structure", id="tab_struct"):
                      yield DataTable(id="dt_market_struct")
        
        with Container(id="log-container"):
            yield Log(id="app-log")
                
        yield Footer()

    def log_msg(self, msg):
        try:
            self.query_one("#app-log", Log).write_line(f"[{get_now_str()}] {msg}")
        except: pass

    last_spot_price = reactive(0.0)

    async def on_mount(self):
        self.last_spot_update_ts = datetime.now().timestamp() # Fix: Init for loop safety
        # Setup Heatmap
        # Heatmap Removed
        # dt_hm = self.query_one("#dt_heatmap", DataTable)
        # dt_hm.add_columns("STRIKE", "D-5", "D-4", "D-3", "D-2", "D-1", "TODAY", "TOTAL Δ")
        
        # Setup Kill Box SPX (Gold Headers)
        dt_spx = self.query_one("#dt_kill_spx", DataTable)
        dt_spx.cursor_type = "row"
        dt_spx.add_columns(
            Text("SPX WHALE TRAPS", style="bold gold"), 
            Text("STRIKE", style="bold gold"), 
            Text("TYPE", style="bold gold"), 
            Text("DTE", style="bold gold"),
            Text("BE", style="bold gold"),   # Restored
            Text("SPOT", style="bold gold"), # Restored
            Text("STATUS", style="bold gold"), 
            Text("NET Δ", style="bold gold"),
            Text("Gamma", style="bold gold"),    # Renamed
            Text("Vega", style="bold gold"),    # Renamed
            Text("Theta", style="bold gold"),    # Renamed
        )
        
        # Setup Kill Box SPY (Cyan Headers)
        dt_spy = self.query_one("#dt_kill_spy", DataTable)
        dt_spy.cursor_type = "row"
        dt_spy.add_columns(
            Text("SPY RETAIL TRAPS", style="bold cyan"), 
            Text("STRIKE", style="bold cyan"), 
            Text("TYPE", style="bold cyan"), 
            Text("DTE", style="bold cyan"),
            Text("BE", style="bold cyan"),   # Restored
            Text("SPOT", style="bold cyan"), # Restored
            Text("STATUS", style="bold cyan"), 
            Text("NET Δ", style="bold cyan"),
            Text("Gamma", style="bold cyan"),    # Renamed
            Text("Vega", style="bold cyan"),    # Renamed
            Text("Theta", style="bold cyan"),    # Renamed
        )
        
        # Setup Market Structure
        dt_struct = self.query_one("#dt_market_struct", DataTable)
        dt_struct.add_columns("METRIC", "LEVEL", "CONTEXT")
        
        await self.refresh_analysis()
        
        # --- SAFETY BRIDGE (ZMQ) ---
        try:
            self.zmq_ctx = zmq.Context()
            self.zmq_pub = self.zmq_ctx.socket(zmq.PUB)
            self.zmq_pub.bind("tcp://*:5559")
            self.log_msg("Safety Bridge: Active (Port 5559)")
        except Exception as e:
            self.log_msg(f"Safety Bridge Error: {e}")

        # --- SENTINEL MONITORING ---
        self.set_interval(30, self.sentinel_loop)
        self.log_msg("Sentinel: Active (30s Scan)")

        await self.refresh_analysis()
        await self.refresh_analysis()
        self.set_interval(3600.0, self.on_hourly_fetch) # HOURLY FETCH TRIGGER

        
        # Start Nexus Feed
        self.run_worker(self.sub_nexus_feed)
        
        # Start API Fallback (for closed markets)
        self.run_worker(self.fetch_fallback_price)

    def sentinel_loop(self):
        """Background monitor for critical market structure changes."""
        spot = self.last_spot_price
        if spot == 0: return
        
        now = datetime.now().timestamp()
        
        # Initialize State Tracking if missing
        if not hasattr(self, 'alert_cooldowns'): self.alert_cooldowns = {}
        if not hasattr(self, 'last_alert_spots'): self.last_alert_spots = {}
        
        def should_alert(key, current_spot, duration=900):
            """
            Checks both time cooldown and price stasis.
            Returns True if we should alert (and updates state).
            """
            # 1. Price Stasis Check (Anti-Spam)
            # If we already alerted on this EXACT price for this key, don't spam.
            last_price = self.last_alert_spots.get(key, -1.0)
            if abs(current_spot - last_price) < 0.01: # Float comparison safety
                return False
                
            # 2. Time Cooldown Check
            last_time = self.alert_cooldowns.get(key, 0)
            if now - last_time > duration:
                # Update State
                self.alert_cooldowns[key] = now
                self.last_alert_spots[key] = current_spot
                return True
            return False

        # 1. MAGNET PROXIMITY
        if hasattr(self, 'last_top_gex'):
            for k, v in self.last_top_gex.items():
                if abs(spot - k) < 0.50:
                    if should_alert(f"MAGNET_{k}", spot):
                        self.send_discord_alert(
                            "🧲 MAGNET PROXIMITY", 
                            f"Spot: ${spot:.2f}\nMagnet: ${k:.2f}\nAction: Watch for Rejection or Breakout.",
                            0xFFFF00 # Yellow
                        )

        # 2. PAIN FLOOR HIT
        pain = getattr(self, 'last_flow_pain', 0)
        if pain > 0 and spot <= pain:
            if should_alert("PAIN_FLOOR", spot):
                self.send_discord_alert(
                    "🩸 PAIN FLOOR HIT",
                    f"Spot: ${spot:.2f}\nPain Lvl: ${pain:.2f}\nAction: Bullish Defense Expected.",
                    0x00FF00 # Green (Opportunity)
                )

        # 3. THESIS INVALIDATION (Updated Threshold)
        if spot > 692.15:
            if should_alert("THESIS_BROKEN", spot, 3600):
                self.send_discord_alert(
                    "🛑 THESIS BROKEN",
                    f"Spot: ${spot:.2f} > $692.15\nAction: INVALIDATION. EXIT SHORTS.",
                    0xFF0000 # Red
                )



    def send_discord_alert(self, title, body, color):
        if not DISCORD_WEBHOOK_URL: return
        try:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": body,
                    "color": color,
                    "footer": {"text": "Nexus Sentinel • Strategic HUD"}
                }]
            }
            requests.post(DISCORD_WEBHOOK_URL, json=payload)
            self.log_msg(f"SENTINEL ALERT: {title}")
        except: pass

    async def on_hourly_fetch(self):
        """Triggered every hour to fetch new data."""
        self.log_msg("⏰ Hourly Fetch Triggered...")
        await self.run_full_fetch_cycle()

    async def run_full_fetch_cycle(self):
        """Runs the fetch sequence with proper staggering."""
        self.log_msg("🔄 Starting Data Fetch Cycle...")
        
        # Run in thread to allow I/O blocking without freezing UI
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.fetch_and_save_snapshots)
        
        # After fetch, refresh analysis
        self.log_msg("✅ Fetch Complete. Updating Analysis...")
        await self.refresh_analysis()

    def fetch_and_save_snapshots(self):
        """
        Fetches ORATS (SPY) and UW (Sweeps) data, saves to CSV.
        Includes STAGGER to prevent rate limits.
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            TICKER_EQUITY = "SPY"
            
            # 1. FETCH SPY (ORATS)
            # --------------------
            self.write_log("⬇️ Fetching SPY Data (ORATS)...")
            orats_strikes = self.get_orats_data('strikes')
            
            if orats_strikes:
                spy_rows = []
                # Fallback price if not found
                current_price = self.last_spot_price if self.last_spot_price > 0 else 600.0
                
                for item in orats_strikes:
                    base_data = {
                        'symbol': 'SPY',
                        'exp': item.get('expiry'),
                        'dte': item.get('dte'),
                        'stk': item.get('strike'),
                        'underlying_price': current_price
                    }
                    
                    # Greeks (Shared or Call-Implied)
                    raw_delta = item.get('delta') or 0
                    raw_gamma = item.get('gamma') or 0
                    raw_vega = item.get('vega') or 0
                    raw_theta = item.get('theta') or 0

                    # Call Row
                    c_row = base_data.copy()
                    c_row.update({
                        'type': 'CALL',
                        'vol': item.get('callVolume', 0),
                        'oi': item.get('callOpenInterest', 0),
                        'delta': raw_delta,
                        'gamma': raw_gamma,
                        'vega': raw_vega,
                        'theta': raw_theta,
                        'prem': 0
                    })
                    # Approx Premium
                    try:
                        mid = (item.get('callBid', 0) + item.get('callAsk', 0)) / 2
                        c_row['prem'] = mid * c_row['vol'] * 100
                    except: pass
                    spy_rows.append(c_row)
                    
                    # Put Row
                    p_row = base_data.copy()
                    # Put Delta Approximation (Call Delta - 1)
                    p_delta = raw_delta - 1.0 if raw_delta != 0 else 0
                    
                    p_row.update({
                        'type': 'PUT',
                        'vol': item.get('putVolume', 0),
                        'oi': item.get('putOpenInterest', 0),
                        'delta': p_delta,
                        'gamma': raw_gamma,
                        'vega': raw_vega,
                        'theta': raw_theta,
                        'prem': 0
                    })
                    try:
                        mid = (item.get('putBid', 0) + item.get('putAsk', 0)) / 2
                        p_row['prem'] = mid * p_row['vol'] * 100
                    except: pass
                    spy_rows.append(p_row)

                if spy_rows:
                    df_spy = pd.DataFrame(spy_rows)
                    os.makedirs("snapshots_spy", exist_ok=True)
                    df_spy.to_csv(f"snapshots_spy/spy_snapshot_{timestamp}.csv", index=False)
                    self.write_log(f"✅ Saved SPY Snapshot: {len(df_spy)} rows")
            else:
                self.write_log("⚠️ SPY Fetch Failed (Empty).")

            # 2. STAGGER (Critical for Rate Limits)
            # -------------------------------------
            self.write_log("⏳ Staggering for 10s...")
            time.sleep(10)

            # 3. FETCH SWEEPS (UW)
            # --------------------
            self.write_log("⬇️ Fetching Sweeps (UW)...")
            
            # Need trading date
            t_date = get_today_date().strftime('%Y-%m-%d')
            uw_params = {'date': t_date}
            
            # Add headers to prevent blocking
            headers = {
                "Authorization": f"Bearer {UW_API_KEY}",
                "User-Agent": "NexusTradingBot/1.0",
                "Accept": "application/json"
            }
            uw_strikes = self.fetch_uw_data(f"https://api.unusualwhales.com/api/stock/{TICKER_EQUITY}/flow-per-strike", uw_params, headers)
            
            if uw_strikes:
                uw_rows = []
                for item in uw_strikes:
                    # Call Row
                    if item.get('call_volume', 0) > 0:
                        uw_rows.append({
                            'ticker': TICKER_EQUITY,
                            'parsed_expiry': item.get('expiry'),
                            'parsed_strike': item.get('strike'),
                            'parsed_type': 'CALL',
                            'total_premium': item.get('call_premium', 0),
                            'total_size': item.get('call_volume', 0),
                            'open_interest': 0 
                        })
                    # Put Row
                    if item.get('put_volume', 0) > 0:
                        uw_rows.append({
                            'ticker': TICKER_EQUITY,
                            'parsed_expiry': item.get('expiry'),
                            'parsed_strike': item.get('strike'),
                            'parsed_type': 'PUT',
                            'total_premium': item.get('put_premium', 0),
                            'total_size': item.get('put_volume', 0),
                            'open_interest': 0
                        })
                
                if uw_rows:
                    df_uw = pd.DataFrame(uw_rows)
                    os.makedirs("snapshots_sweeps", exist_ok=True)
                    df_uw.to_csv(f"snapshots_sweeps/uw_flow_snapshot_{timestamp}.csv", index=False)
                    self.write_log(f"✅ Saved UW Snapshot: {len(df_uw)} rows")
            else:
                 self.write_log("⚠️ UW Fetch Failed.")

        except Exception as e:
            self.write_log(f"❌ FETCH ERROR: {e}")
            # traceback.print_exc()

    def get_orats_data(self, endpoint_type):
        api_url = f"https://api.orats.io/datav2/live/{endpoint_type}"
        params = {'token': ORATS_API_KEY.strip(), 'ticker': 'SPY'}
        try:
            response = requests.get(api_url, params=params, timeout=15)
            if response.status_code == 429:
                self.write_log(f"⚠️ ORATS Rate Limit ({endpoint_type}).")
                return None
            response.raise_for_status()
            data = response.json()
            result_data = data.get('data', data)
            if result_data == [] or result_data == {}: return None
            return result_data if result_data else None
        except Exception as e:
            self.write_log(f"ORATS Error: {e}")
            return None

    def fetch_uw_data(self, url, params, headers=None):
        if headers is None: headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.write_log(f"UW Error: {e}")
            return None

    async def fetch_fallback_price(self):
        """Fetch snapshot from TradeStation API if stream is silent."""
        if not TradeStationManager or not TS_CLIENT_ID:
            self.log_msg("API Fallback: Config missing.")
            return

        self.log_msg("API Fallback: Fetching SPY Snapshot...")
        try:
            # Run in thread to avoid blocking UI
            def _fetch():
                ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
                return ts.get_quote_snapshot("SPY")
            
            loop = asyncio.get_event_loop()
            quote = await loop.run_in_executor(None, _fetch)
            
            if quote:
                price = float(quote.get('Last', 0))
                if price > 0:
                    self.last_spot_price = price
                    self.log_msg(f"API Fallback: SPY ${price:.2f}")
                else:
                    self.log_msg("API Fallback: Price is 0.00")
            else:
                self.log_msg("API Fallback: No quote returned.")
        except Exception as e:
            self.log_msg(f"API Fallback Error: {e}")

    async def sub_nexus_feed(self):
        """Listen to Nexus Execution Engine for Live SPY Price"""
        # Port 5555 is ZMQ_PORT_MARKET in ts_nexus.py
        try:
            ctx = zmq.asyncio.Context()
            sub = ctx.socket(zmq.SUB)
            sub.connect("tcp://127.0.0.1:5555")
            sub.subscribe(b"SPY")
            self.log_msg("Nexus Feed: Connected (Port 5555)")
            
            while True:
                msg = await sub.recv_multipart()
                # msg[0] = topic (SPY), msg[1] = payload (JSON)
                try:
                    data = json.loads(msg[1].decode('utf-8'))
                    if 'Last' in data:
                        price = float(data['Last'])
                        if price > 0:
                            self.last_spot_price = price
                            self.last_spot_update_ts = datetime.now().timestamp() # Track Freshness
                            # Optional: Log only on significant change to avoid spam
                            # self.log_msg(f"Nexus Tick: ${price:.2f}")
                            self.last_spot_update_ts = datetime.now().timestamp()
                except: pass
                
                # FALLBACK POLLING (If Stale > 30s)
                now = datetime.now().timestamp()
                if now - self.last_spot_update_ts > 30:
                    try:
                        # Non-blocking check to simple fallback file or direct API
                        # Using direct API here might be too heavy for this loop if it blocks.
                        # Instead, we rely on the refresh button or a separate worker.
                        # Let's add a periodic check in the loop every 30s
                        await self.fetch_direct_price()
                        # Update TS so we don't spam
                        self.last_spot_update_ts = datetime.now().timestamp()
                    except: pass
                    
        except Exception as e:
            self.log_msg(f"Nexus Feed Error: {e}")

    async def fetch_direct_price(self):
        """Fetches SPY price directly from TradeStation API as fallback."""
        try:
            if 'TradeStationManager' not in globals(): return
            
            # Run in executor to avoid blocking the UI/ZMQ loop
            loop = asyncio.get_event_loop()
            def _poll():
                ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
                q = ts.get_quote_snapshot("SPY")
                return float(q.get('Last', 0))
            
            price = await loop.run_in_executor(None, _poll)
            if price > 0:
                self.last_spot_price = price
                # self.log_msg(f"Direct Feed: ${price:.2f}") # Debug
        except Exception as e:
            # self.log_msg(f"Fallback Error: {e}")
            pass

    @on(Button.Pressed, "#btn_refresh")
    async def on_refresh(self):
        # Trigger explicit fetch on click
        await self.run_full_fetch_cycle()

    async def refresh_analysis(self):
        if getattr(self, "is_refreshing", False):
            self.log_msg("⚠️ Analysis already in progress. Ignoring request.")
            return

            
        self.is_refreshing = True
        self.log_msg("🚀 Refreshing Analysis (Fast Load)...")
        
        try:
            # --- PHASE 1: IMMEDIATE (TODAY ONLY) ---
            # Run in thread to allow UI to breathe even for the small load
            loop = asyncio.get_event_loop()
        
            # Load Day 0 (Today)
            # Note: we use 0 days_back to get just today/yesterday depending on midnight. 
            # Actually load_unified_data logic: days_back=1 includes cutoff from yesterday.
            # Let's use 1 to be safe for T-24h
            today_df = await loop.run_in_executor(None, load_unified_data, 1, None)
            
            if not today_df.empty:
                self.current_df = today_df
                self.daily_stats = analyze_persistence(today_df)
                
                # Update Active Traps IMMEDIATELY
                live_spy = self.last_spot_price
                live_spx = live_spy * 10.03 
                if 'underlying_price' in today_df.columns:
                     spx_rows = today_df[today_df['ticker'] == 'SPX']
                     if not spx_rows.empty:
                         last_spx = spx_rows['underlying_price'].iloc[-1]
                         if last_spx > 0 and abs(last_spx - (live_spy*10)) < 100: 
                            live_spx = float(last_spx)
    
                await self.build_kill_box(live_spx=live_spx, live_spy=live_spy)
                self.log_msg("✅ Active Traps Updated.")
        except Exception as e:
            self.log_msg(f"❌ Analysis Error (Phase 1): {e}")
            self.is_refreshing = False
            return
        
        # --- PHASE 2: BACKGROUND (HISTORY) ---
        # Offload deep history to background so UI is interactive
        self.run_worker(self.load_history_background)

    async def load_history_background(self):
        try:
            self.log_msg("⏳ Loading 10-Day History in Background...")
            loop = asyncio.get_event_loop()
            full_df = await loop.run_in_executor(None, load_unified_data, 10, None)
            
            if full_df.empty:
                 self.log_msg("⚠️ History Load Empty.")
                 return
                 
            self.current_df = full_df
            self.daily_stats = analyze_persistence(full_df)
            
            self.log_msg("📊 History Loaded. Updating Heatmaps & Narrative...")
            
            # Update Full UI
            self.update_header_metrics()
            # self.build_heatmap()
            self.build_market_structure()
            
            # Re-run Traps just in case history changed context (Fortress checks etc)
            # But we keep the live prices we already have
            live_spy = self.last_spot_price
            live_spx = live_spy * 10.03
            await self.build_kill_box(live_spx=live_spx, live_spy=live_spy)
            
            # Trajectory
            traj_msg = self.calculate_trajectory()
            self.query_one("#narrative-box", Static).update(traj_msg)
            
            self.check_divergence()
            self.query_one("#last-updated-lbl", Label).update(get_now_str())
            self.log_msg("✅ Analysis Complete.")
            self.build_market_structure()
            
            # --- TRAJECTORY ENGINE ---
            traj_msg = self.calculate_trajectory()
            self.query_one("#narrative-box", Static).update(traj_msg)

        except Exception as e:
            self.log_msg(f"❌ History Load Error: {e}")
        finally:
            self.is_refreshing = False
            self.log_msg("✅ Cycle Ready.")
        


    def update_header_metrics(self):
        # Narrative Generation
        narrative = generate_expiry_narrative(self.current_df)
        self.query_one("#narrative-box", Static).update(narrative)
        
        # Sentiment Score (Keep calculation for Regime logic, but remove UI bar)
        total_prem = self.current_df['premium'].sum()
        bull_prem = self.current_df[self.current_df['is_bull']]['premium'].sum()
        
        score = (bull_prem / total_prem * 100) if total_prem > 0 else 50
        self.sentiment_score = score
        
        # Market Regime
        # Short Vol: High Put Selling (Bearish Sentiment but Price Stable/Up? Or just High Put Premium with 'SELL' tag)
        # For simplicity: 
        # Gamma Squeeze: High Call Buying (Score > 70)
        # Liquidation: Negative OI Delta across board
        # Short Vol: High Put Premium
        
        regime = "NEUTRAL"
        if score > 65: regime = "GAMMA SQUEEZE"
        elif score < 35: regime = "BEARISH FLOW"
        
        # Check Liquidation (Total OI Delta)
        total_oi_delta = self.daily_stats['oi_delta'].sum()
        if total_oi_delta < -50000: regime = "LIQUIDATION"
        
        self.market_regime = regime
        self.query_one("#regime-lbl", Label).update(regime)
        
        # Color Regime
        reg_style = "bold green" if "SQUEEZE" in regime else ("bold red" if "BEAR" in regime or "LIQUID" in regime else "bold yellow")
        self.query_one("#regime-lbl", Label).styles.color = "green" if "SQUEEZE" in regime else "red" # Simple CSS color

    def build_heatmap(self):
        # REMOVED
        pass

    async def build_kill_box(self, live_spx=0.0, live_spy=0.0):
        dt_spx = self.query_one("#dt_kill_spx", DataTable)
        dt_spy = self.query_one("#dt_kill_spy", DataTable)
        dt_spx.clear()
        dt_spy.clear()
        
        # Define Spot Prices (Prioritize Arguments -> Internal Live -> Fallback)
        fallback_spy = 600.0 
        SPY_PRICE = live_spy if live_spy > 0 else (self.last_spot_price if self.last_spot_price > 0 else fallback_spy)
        # SPX: Use arg, or derive
        SPX_PRICE = live_spx if live_spx > 0 else (SPY_PRICE * 10.03)
        
        # FILTER: Only Active Contracts for Kill Box
        try:
            today_ts = pd.Timestamp(get_today_date())
            # Ensure expiry_dt exists (it might not if we removed the global purge)
            if 'expiry_dt' not in self.current_df.columns:
                self.current_df['expiry_dt'] = pd.to_datetime(self.current_df['expiry'], errors='coerce')
            
            # [FIX] Fill NaT expiry with calculated date (Date + DTE)
            mask_nat = self.current_df['expiry_dt'].isna()
            if mask_nat.any():
                # Ensure date is datetime64
                self.current_df['date'] = pd.to_datetime(self.current_df['date'])
                self.current_df.loc[mask_nat, 'expiry_dt'] = self.current_df.loc[mask_nat, 'date'] + pd.to_timedelta(self.current_df.loc[mask_nat, 'dte'], unit='D')
            
            active_df = self.current_df[self.current_df['expiry_dt'] >= today_ts].copy()
            
            # [FIX] Filter Extreme OTM (Junk Data)
            # Example: $1000 Strike SPY when Spot is $690 is +45% OTM.
            # Filter: Keep Strikes within +/- 30% of Spot.
            eff_spx = SPX_PRICE if SPX_PRICE > 2000 else (SPY_PRICE * 10.0)
            eff_spy = SPY_PRICE

            cond_spx = (active_df['ticker'] == 'SPX') & (active_df['strike'].between(eff_spx * 0.7, eff_spx * 1.3))
            cond_spy = (active_df['ticker'] == 'SPY') & (active_df['strike'].between(eff_spy * 0.7, eff_spy * 1.3))
            
            # Keep if it meets condition OR if it's not SPX/SPY (future proof)
            active_df = active_df[cond_spx | cond_spy]

        except Exception as e:
            self.log_msg(f"⚠️ Filter Active Traps Error: {e}")
            active_df = self.current_df.copy() # Fallback
        
        # 1. PROCESS CALLS (Bull Traps)
        calls = active_df[active_df['type'] == 'CALL'].groupby(['ticker', 'strike', 'expiry', 'dte']).agg({
            'premium': 'sum', 'vol': 'sum', 'oi': 'max', 'delta': 'mean', 'gamma': 'mean', 'vega': 'mean', 'theta': 'mean'
        }).reset_index()
        calls['oi_delta'] = calls['oi'] * calls['delta'] * 100.0
        calls['avg_prem'] = calls['premium'] / calls['vol'].replace(0, 1)
        calls['breakeven'] = calls['strike'] + (calls['avg_prem'] / 100.0)
        calls['type'] = 'CALL' 
        # Call Trap: Price < Breakeven
        calls['status'] = calls.apply(lambda x: "TRAPPED BULLS" if (SPY_PRICE if x['ticker']=='SPY' else SPX_PRICE) < x['breakeven'] else "PROFIT", axis=1)

        # 2. PROCESS PUTS (Bear Traps) -- NEW LOGIC
        puts = active_df[active_df['type'] == 'PUT'].groupby(['ticker', 'strike', 'expiry', 'dte']).agg({
            'premium': 'sum', 'vol': 'sum', 'oi': 'max', 'delta': 'mean', 'gamma': 'mean', 'vega': 'mean', 'theta': 'mean'
        }).reset_index()
        puts['oi_delta'] = puts['oi'] * puts['delta'] * 100.0
        puts['avg_prem'] = puts['premium'] / puts['vol'].replace(0, 1)
        # Put Breakeven = Strike - Premium
        puts['breakeven'] = puts['strike'] - (puts['avg_prem'] / 100.0)
        puts['type'] = 'PUT' 
        # Put Trap: Price > Breakeven
        puts['status'] = puts.apply(lambda x: "TRAPPED BEARS" if (SPY_PRICE if x['ticker']=='SPY' else SPX_PRICE) > x['breakeven'] else "PROFIT", axis=1)

        # 3. MERGE & FILTER
        merged = pd.concat([calls, puts], ignore_index=True)
        trapped = merged[merged['status'].str.contains("TRAPPED")].copy()
        
        # --- NEW: CAPITULATION INDEX (Days to Zero) ---
        # Formula: (Avg Premium (x100 for $) / 100) / |Theta (Daily)|  -> actually Premium is usually Total Premium Amount.
        # Data: 'avg_prem' is typically cents/dollars per share. 'theta' is typically dollar decay per option per day.
        # Let's align units.
        # 'premium' load code says: item['total_premium'] or item['prem']. Standardized to 'premium'.
        # 'avg_prem' calculation above: premium / vol. 
        # If 'premium' is total notional premium, and vol is volume, avg_prem is premium per contract.
        # 'theta' from TS or Polygon is typically decay *per contract*.
        
        # Safe Division for Days Left
        def calc_days_left(row):
            # Theta is negative burn.
            burn = abs(row['theta'])
            if burn < 0.01: return 999.0 # Effectively infinite / no decay
            
            # Premium per share = avg_prem. Option is 100 shares.
            # Usually Theta is quoted as "price change per share" or "premium change".
            # If option price is $1.50, Theta might be -0.05.
            # So Days = 1.50 / 0.05 = 30 days.
            # Our 'avg_prem' is derived from Total Premium / Volume.
            # If Total Premium was $15,000 for 100 contracts ($1.50 * 100 * 100), avg_prem would be $150.
            # We need to verify unit scaling in `load_unified_data`. 
            # Logic there: `std_df['premium'] = ...`
            # For simplicity, let's assume `avg_prem` is correct "Dollars per Contract" or "Cents".
            # Wait, `calls['breakeven'] = calls['strike'] + (calls['avg_prem'] / 100.0)` implies avg_prem is scaled x100 (e.g. $150 for $1.50 price).
            # So Price = avg_prem / 100. 
            # Theta is usually price change.
            
            price = row['avg_prem'] / 100.0
            
            # [FIX] If Volume is 0, Price is 0. This creates False Positive Liquidation (0 Days).
            if price <= 0.001: return 999.0

            return price / burn

        trapped['days_left'] = trapped.apply(calc_days_left, axis=1)
        
        # Status Enrichment
        def enhance_status(row):
            s = row['status']
            # [FIX] Ignore Long-Dated options for Liquidation Panic (likely bad data matching)
            if row['dte'] > 7: return s

            if row['days_left'] < 2.0: return f"💀 LIQUIDATION" # Extreme Urgency
            if row['days_left'] < 5.0: return f"🔥 BURNING"     # High Urgency
            return s # Restore full text (TRAPPED BULLS)
            
        trapped['display_status'] = trapped.apply(enhance_status, axis=1)
        # ----------------------------------------------
        
        if trapped.empty:
            merged['display_status'] = "SUPPORT/RESIST"
            merged['days_left'] = 999
            trapped = merged.sort_values('oi', ascending=False).head(20)
        
        # Sort by OI Delta (Pain)
        trapped['abs_exposure'] = trapped['oi_delta'].abs()
        spx_traps = trapped[trapped['ticker'] == 'SPX'].sort_values(by=['abs_exposure'], ascending=False).head(20)
        spy_traps = trapped[trapped['ticker'] == 'SPY'].sort_values(by=['abs_exposure'], ascending=False).head(20)
        
        # --- ENRICH WITH GREEKS ---
        # (Using imported module)
        try:
             trapped = enrich_traps_with_greeks(trapped)
             self.log_msg("✅ Live Greeks Enriched.")
        except Exception as e:
             self.log_msg(f"⚠️ Greek Enrichment Failed: {e}")
        
        # Populate Tables
        # Col Schema: Ticker, Strike, Type, DTE, Status, Net Delta, Rent, Days Left
        
        for dt, data in [(dt_spx, spx_traps), (dt_spy, spy_traps)]:
            for _, row in data.iterrows():
                # Styling
                is_call = row['type'] == 'CALL'
                type_style = "green" if is_call else "red"
                
                # Status Style
                s_txt = row['display_status']
                if "LIQUIDATION" in s_txt: s_style = "bold white on red"
                elif "BURNING" in s_txt: s_style = "bold red"
                elif "TRAPPED BULLS" in s_txt: s_style = "green"
                elif "TRAPPED BEARS" in s_txt: s_style = "red"
                else: s_style = "yellow"

                
                # Delta Style
                d_val = row['oi_delta']
                d_str = fmt_notional(d_val, show_plus=True)
                d_style = "green" if d_val > 0 else "red"
                
                # Greeks Formatting (Safe Handling)
                def clean_greek(val):
                    f = float(row.get(val, 0))
                    if pd.isna(f): return 0.0
                    return f
                
                gamma = clean_greek('gamma')
                vega = clean_greek('vega')
                theta_raw = clean_greek('theta')

                # Rent Style (Safe)
                if theta_raw == 0: 
                    rent_str = "-"
                    rent_val = 0
                else:
                    rent_val = abs(theta_raw)
                    rent_str = f"-${rent_val:.2f}"
                
                r_style = "red" if rent_val > 0.10 else "dim white"

                # Days Left Style (Safe)
                days = row.get('days_left', 999)
                if pd.isna(days) or days == float('inf') or days > 900: 
                    day_str = "-"
                    day_style = "dim white"
                else:
                    day_str = f"{days:.1f}d"
                    day_style = "bold red" if days < 5 else "green"

                dt.add_row(
                    Text(row['ticker'], style="bold white"),
                    Text(f"{row['strike']:.0f}", style="cyan"),
                    Text(row['type'], style=type_style),
                    Text(f"{row['dte']:.0f}", style="white"),
                    Text(f"${row['breakeven']:.2f}", style="white"),
                    Text(f"${SPX_PRICE if row['ticker']=='SPX' else SPY_PRICE:.2f}", style="dim white"),
                    Text(s_txt, style=s_style),
                    Text(d_str, style=d_style),
                    Text(f"{gamma:.4f}", style="dim white"),
                    Text(f"{vega:.4f}", style="dim white"),
                    Text(f"{theta_raw:.4f}", style="dim white"),
                )
        try:
             self.log_msg("🌉 Bridging Data to Quant Engine...")
             # Combine SPX and SPY for bridge (assuming they have 'ticker' col)
             combined_bridge_df = pd.concat([spx_traps, spy_traps], ignore_index=True)
             
             # Lazy import to avoid circular dependency at top level
             from quant_bridge import build_quant_payload
             
             quant_payload = build_quant_payload(combined_bridge_df)
             
             # Save to disk for Auditor
             with open("nexus_quant.json", "w") as f:
                 json.dump(quant_payload, f, indent=2)
                 
             self.log_msg("✅ Quant Bridge Exported.")
             
        except Exception as e:
             self.log_msg(f"⚠️ Quant Bridge Failed: {e}")

        # --------------------------
        
        # [CLEANUP] Duplicate logic removed.

    def build_market_structure(self):
        dt = self.query_one("#dt_market_struct", DataTable)
        dt.clear()
        
        if self.current_df.empty: return
        
        # Use Standalone Logic
        spot = self.last_spot_price if self.last_spot_price > 0 else 600.0
        metrics = calculate_market_structure_metrics(self.current_df, spot)
        
        # Store for Trajectory
        self.last_flow_pain = metrics['flow_pain']
        self.last_top_gex = metrics['top_gex']
        
        # --- SMA INTEGRATION (NEW) ---
        structure_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_structure.json")
        try:
             with open(structure_path, "r") as f:
                 structure_data = json.load(f)
                 levels = structure_data.get("levels", {})
                 
                 # Display Key Levels
                 vwap = levels.get("vwap", 0)
                 sma20 = levels.get("sma_20", 0)
                 sma50 = levels.get("sma_50", 0)
                 sma200 = levels.get("sma_200", 0)
                 
                 if vwap > 0: dt.add_row("VWAP", f"${vwap:.2f}", "Session Avg Price")
                 if sma20 > 0: dt.add_row("SMA 20", f"${sma20:.2f}", "Short-Term Trend")
                 if sma50 > 0: dt.add_row("SMA 50", f"${sma50:.2f}", "Mid-Term Trend")
                 if sma200 > 0: dt.add_row("SMA 200", f"${sma200:.2f}", "Long-Term Trend")
                 
        except Exception as e:
            self.write_log(f"[WARN] Failed to load structure data: {e}")
        # -----------------------------
        
        # Populate UI
        if self.last_flow_pain > 0:
            dt.add_row("FLOW PAIN", f"${self.last_flow_pain:.2f}", "Todays Trader Pain Lvl")
        else:
            dt.add_row("WARNING", "NO GAMMA DATA", "GEX calc impossible")

        for k, v in self.last_top_gex.items():
            fmt_v = f"${v/1e6:.1f}M" 
            tag = "Call Flow" if v > 0 else "Put Flow"
            dt.add_row(f"FLOW MAGNET ({tag})", f"${k:.2f}", f"{fmt_v} Net Exposure")

    def calculate_trajectory(self):
        spot = self.last_spot_price
        pain = getattr(self, 'last_flow_pain', 0)
        top_gex = getattr(self, 'last_top_gex', pd.Series(dtype=float))
        
        return calculate_trajectory_logic(spot, pain, top_gex, self.current_df)

    def check_divergence(self):
        div_detected = check_divergence_logic(self.daily_stats, self.sentiment_score)
        
        if div_detected:
            self.divergence_alert = div_detected
            self.query_one("#div-lbl", Label).update(div_detected)
            self.query_one("#div-lbl", Label).styles.color = "green" if "BULL" in div_detected else "red"
            
            # Border Alert
            color = "green" if "BULL" in div_detected else "red"
            self.screen.styles.border = ("heavy", color)
            self.write_log(f"[CRITICAL] MARKET DIVERGENCE DETECTED: {div_detected}")
        else:
            self.divergence_alert = None
            self.query_one("#div-lbl", Label).update("NONE")
            self.query_one("#div-lbl", Label).styles.color = "white"
            self.screen.styles.border = None

    def write_log(self, msg):
        # No log widget in new design, print to console or add one?
        # User asked for "Log a warning". I'll print to stdout for now or add a hidden log.
        print(f"[{get_now_str()}] {msg}")

    @on(Button.Pressed, "#btn_snapshot")
    def on_snapshot(self):
        # ... (Existing snapshot logic) ...
        pass

# --- STANDALONE LOGIC FUNCTIONS ---
def calculate_market_structure_metrics(df, spot_price):
    """Calculates Flow Pain and Top GEX Levels."""
    results = {'flow_pain': 0, 'top_gex': pd.Series(dtype=float)}
    
    if df.empty: return results
    
    # Filter for SPY
    spy_df = df[df['ticker'] == 'SPY'].copy()
    if spy_df.empty: return results

    # 1. SAFETY CHECK: Missing Gamma
    if 'gamma' not in spy_df.columns or spy_df['gamma'].sum() == 0:
         return results

    spot = spot_price if spot_price > 0 else 600.0
    
    # 2. FLOW GEX CALCULATION
    spy_df['flow_gex'] = spy_df['gamma'] * spy_df['vol'] * spot * 100
    gex_profile = spy_df.groupby('strike')['flow_gex'].sum().sort_index()

    
    # 3. FLOW PAIN
    try:
        strikes = sorted(spy_df['strike'].unique())
        pain_map = {}
        for k in strikes:
            calls = spy_df[spy_df['type'] == 'CALL']
            puts = spy_df[spy_df['type'] == 'PUT']
            call_val = (k - calls['strike']).clip(lower=0) * calls['vol']
            put_val = (puts['strike'] - k).clip(lower=0) * puts['vol']
            pain_map[k] = call_val.sum() + put_val.sum()
        
        if pain_map:
            results['flow_pain'] = min(pain_map, key=pain_map.get)
    except: pass

    # 4. FLOW MAGNETS
    results['top_gex'] = gex_profile.abs().nlargest(3)
    return results

def calculate_trajectory_logic(spot_price, flow_pain, top_gex, df):
    """Calculates Trajectory, Magnet, and Drift."""
    if spot_price == 0: return "WAITING FOR DATA"
    
    # 1. PRESSURE
    pressure = "NEUTRAL"
    if flow_pain > 0:
        if spot_price < flow_pain: pressure = "BEARISH DRAG (Price < Pain)"
        else: pressure = "BULLISH COMPRESSION (Price > Pain)"
        
    # 2. MAGNETISM
    magnet = "NONE"
    if not top_gex.empty:
        biggest_strike = top_gex.abs().idxmax()
        magnet = f"${biggest_strike:.2f}"
        
    # 3. CHARM (Drift)
    drift = "NEUTRAL"
    try:
        short_df = df[df['dte'] < 7]
        if not short_df.empty:
            calls = short_df[short_df['type'] == 'CALL']['vol'].sum()
            puts = short_df[short_df['type'] == 'PUT']['vol'].sum()
            if calls > puts * 1.2: drift = "BEARISH (Dealer Hedging)"
            elif puts > calls * 1.2: drift = "BULLISH (Dealer Hedging)"
    except: pass
    
    return f"TRAJECTORY: {pressure} | Magnet: {magnet} | Drift: {drift}"

def check_divergence_logic(daily_stats, sentiment_score):
    """Checks for Market Divergence."""
    div_detected = None
    try:
        fortress_calls = daily_stats[(daily_stats['is_fortress']) & (daily_stats['is_bull'])].shape[0]
        if fortress_calls > 2 and sentiment_score < 40:
            div_detected = "BULL DIV"
    except: pass
    return div_detected

# --- HEADLESS EXECUTION ---
def antigravity_dump(filename, data_dictionary):
    """Atomically dumps data to a JSON file."""
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, "w") as f: json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
        print(f"✅ [HISTORY] Wrote {filename}")
    except Exception as e:
        print(f"❌ HISTORY DUMP ERROR: {e}")

def run_headless_analysis():
    print("🧠 Starting Long-Term Memory Analysis Service (Loop 60m)...")
    import time
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧠 Running Analysis Cycle...")
            # 1. Load Data (5 Days)
            df = load_unified_data(5)
            
            if not df.empty:
                # 2. Analyze Persistence
                daily_stats = analyze_persistence(df)
                
                # Determine actual history length
                unique_dates = sorted(list(set([d.strftime('%Y-%m-%d') for d in df['date'] if pd.notnull(d)])))
                days_count = len(unique_dates)
                
                # 3. Calculate Trend Signals
                total_oi_delta = daily_stats['oi_delta'].sum()
                
                total_prem = df['premium'].sum()
                bull_prem = df[df['is_bull']]['premium'].sum()
                sentiment_score = (bull_prem / total_prem * 100) if total_prem > 0 else 50
                
                net_flow = df[df['is_bull']]['premium'].sum() - df[~df['is_bull']]['premium'].sum()
                
                level_stats = daily_stats.groupby('strike')['oi_delta'].sum().sort_values(ascending=False)
                major_support = level_stats.head(1).index[0] if not level_stats.empty else 0
                major_resistance = level_stats.tail(1).index[0] if not level_stats.empty else 0
                
                # Cold Start Logic
                trend_label = f"{days_count}-Day Trend"
                if days_count < 2:
                    trend_status = "INSUFFICIENT_DATA"
                    flow_dir = "UNKNOWN"
                else:
                    trend_status = "ACCUMULATION" if total_oi_delta > 0 else "DISTRIBUTION"
                    flow_dir = "BULLISH_TREND" if net_flow > 0 else "BEARISH_TREND"

                # --- NEW: HEADER LOGIC (Trajectory, Divergence) ---
                # Need Spot Price. Try to get from DF or assume 0 (which returns WAITING)
                spot_price = 0.0
                try:
                    spy_df = df[df['ticker'] == 'SPY']
                    if not spy_df.empty and 'underlying_price' in spy_df.columns:
                        last_price = spy_df['underlying_price'].iloc[-1]
                        if last_price > 0: spot_price = float(last_price)
                except: pass

                struct_metrics = calculate_market_structure_metrics(df, spot_price)
                trajectory = calculate_trajectory_logic(spot_price, struct_metrics['flow_pain'], struct_metrics['top_gex'], df)
                divergence = check_divergence_logic(daily_stats, sentiment_score)
                # --------------------------------------------------

                history_state = {
                    "script": "snapshot_analyzer",
                    "trend_signals": {
                        "trend_label": trend_label,
                        "oi_trend": trend_status,
                        "oi_delta_cumulative": total_oi_delta,
                        "sentiment_score": round(sentiment_score, 1),
                        "flow_direction": flow_dir,
                        "net_flow_cumulative": net_flow,
                        "days_analyzed": days_count,
                        # NEW FIELDS
                        "trajectory": trajectory,
                        "divergence": divergence,
                        "flow_pain": struct_metrics['flow_pain']
                    },
                    "persistent_levels": {
                        "major_support": major_support,
                        "major_resistance": major_resistance
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                antigravity_dump("nexus_history.json", history_state)
            else:
                print("⚠️ No history found (Data < 5 days old). Sleeping...")

        except Exception as e:
            print(f"❌ HEADLESS ANALYSIS FAILED: {e}")
            import traceback
            traceback.print_exc()
        
        # Sleep for 1 hour
        time.sleep(3600)

if __name__ == "__main__":
    print(f"🔵 ANALYZE SNAPSHOTS LAUNCHING... Args: {sys.argv}", flush=True)
    import sys
    if "--headless" in sys.argv:
        print("🔵 HEADLESS MODE DETECTED", flush=True)
        run_headless_analysis()
    else:
        print("🔵 TUI MODE DETECTED", flush=True)
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
        app = StrategicHUD()
        app.run()