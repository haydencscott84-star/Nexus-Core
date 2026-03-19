# FILE: analyze_snapshots.py
import nexus_lock
print("🔵 ANALYZE SNAPSHOTS v2026.02.06_FIXED_V2 Loading...", flush=True)
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
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID, DISCORD_WEBHOOK_URL, ZMQ_PORT_NOTIFICATIONS
    # Access API Keys from nexus_config or env if available, else hardcode fallback (safe for local)
    ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
    
    # --- ZMQ NOTIFICATION SETUP ---
    ctx_notify = zmq.Context()
    sock_notify = ctx_notify.socket(zmq.PUSH)
    sock_notify.connect(f"tcp://localhost:{ZMQ_PORT_NOTIFICATIONS}")
    
    def zmq_discord_alert(title, msg, color="BLUE"):
        """Fire-and-Forget ZMQ Notification"""
        try:
            payload = {
                "title": title,
                "message": msg,
                "color": color
            }
            sock_notify.send_json(payload, flags=zmq.NOBLOCK)
        except Exception as e:
            pass # Never crash the math loop
except ImportError:
    TradeStationManager = None
    TS_CLIENT_ID = None
    DISCORD_WEBHOOK_URL = None
    ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

# --- GREEKS ENRICHMENT ---
try:
    from enrich_with_greeks import enrich_traps_with_greeks
except ImportError:
    def enrich_traps_with_greeks(df): return df

def fmt_oi_delta(val):
    abs_val = abs(val)
    if abs_val >= 1_000_000_000: return f"{val/1_000_000_000:+.1f}B"
    if abs_val >= 1_000_000: return f"{val/1_000_000:+.1f}M"
    if abs_val >= 1_000: return f"{val/1_000:+.1f}K"
    return f"{val:+.1f}"

def fmt_notional(val, show_plus=True):
    if pd.isna(val): return "-"
    abs_val = abs(val)
    if abs_val >= 1_000_000_000:
        s = f"{val/1_000_000_000:.1f}B"
    elif abs_val >= 1_000_000:
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
    'spy': 'snapshots_spy',       
    'spx': 'snapshots'            
}

# --- ENGINE ---
def load_unified_data(days_back, log_func=None):
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
        
        # [FIX] Sort by Date and Limit to Last 50 Files (Prevent OOM)
        sorted_dates = sorted(latest_files_map.keys())
        # Keep only the last 50 dates to avoid memory explosion
        if len(sorted_dates) > 50:
            sorted_dates = sorted_dates[-50:]
            
        unique_files = [latest_files_map[d] for d in sorted_dates]
        
        try:
            with open("/root/loader_debug.log", "a") as lf:
                lf.write(f"SOURCE: {source_name} | Cutoff: {cutoff} | Found: {len(unique_files)} files\n")
        except: pass

        
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
                    try:
                        with open("/root/loader_debug.log", "a") as lf:
                            lf.write(f"LOADING: {os.path.basename(f)}\n")
                    except: pass
                    
                    df = pd.read_csv(f)
                    if df.empty: continue

                    # [FIX] POISON PILL: Drop artificial 600.0 placeholders ONLY from SPX
                    if 'underlying_price' in df.columns and source_name == 'spx':
                        df = df[~df['underlying_price'].between(599.9, 600.1)]
                        if df.empty: continue

                    files_loaded += 1
                    
                    # Standardize Columns
                    std_df = pd.DataFrame(index=df.index) # Fix: Initialize with index to allow scalar broadcasting
                    std_df['date'] = file_date
                    
                    # [FIX] Initialize GREEKS with Defaults to prevent KeyError if source block skipped
                    for col in ['gamma', 'delta', 'vega', 'theta', 'vol', 'oi', 'premium']:
                        std_df[col] = 0.0
                    
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
                                                
                            if 'price' in df.columns:
                                std_df['underlying_price'] = pd.to_numeric(df['price'], errors='coerce').fillna(0)
                            else:
                                std_df['underlying_price'] = 0.0

                    elif source_name in ['spy', 'spx']:
                        # Map columns based on inspection:
                        # SPY: ['symbol', 'exp', 'dte', 'stk', 'type', 'prem', 'vol', 'oi', 'voi_ratio', 'edge', 'conf', 'win']
                        # SPX: ['sym', 'exp', 'dte', 'stk', 'type', 'side_tag', 'prem', 'vol', 'oi', 'edge', 'conf', 'win']
                        std_df['ticker'] = source_name.upper()
                        std_df['strike'] = pd.to_numeric(df['stk'], errors='coerce')

                        if 'underlying_price' in df.columns:
                            std_df['underlying_price'] = pd.to_numeric(df['underlying_price'], errors='coerce').fillna(0)
                        else:
                            start_price = float(df['underlying_price'].iloc[0]) if 'underlying_price' in df.columns and not df.empty else 0.0
                            std_df['underlying_price'] = start_price

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
    try:
        with open("/root/loader_debug.log", "a") as lf:
            lf.write(f"CONCATENATING {len(master_dfs)} DATAFRAMES...\n")
    except: pass

    if not master_dfs:
        if log_func: log_func("⚠️ No data loaded from any source.")
        return pd.DataFrame()
        
    master = pd.concat(master_dfs, ignore_index=True)
    
    try:
        with open("/root/loader_debug.log", "a") as lf:
            lf.write(f"CONCAT DONE. ROWS: {len(master)}\n")
    except: pass
    
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
    
    # [OPTIMIZATION] Vectorized Ticker Correction
    # price = row.get('underlying_price', 0) -> vectorized access
    if 'underlying_price' not in master.columns: master['underlying_price'] = 0.0
    
    # Conditions
    # Conditions
    cond_spx_price = master['underlying_price'] > 2000
    cond_spy_price = (master['underlying_price'] > 10) & (master['underlying_price'] < 1500)
    cond_spx_strike = master['strike'] > 1500 # Revert to 1500 because we have poison pill now
    
    # Apply Logic: SPX (Strike) -> SPX (Price) -> SPY (Price) -> Original
    # [FIX] Do NOT overwrite explicitly sourced 'SPY' or 'SPX' data with price heuristics that misclassify OTM SPX options.
    # Only re-classify ambiguously labeled data (e.g. from sweeps).
    mask = ~master['ticker'].isin(['SPX', 'SPY'])
    criteria = [cond_spx_strike & mask, cond_spx_price & mask, cond_spy_price & mask]
    choices = ['SPX', 'SPX', 'SPY']
    
    master['ticker'] = np.select(criteria, choices, default=master['ticker'])

    # [OPTIMIZATION] Vectorized Norm Strike
    master['norm_strike'] = np.where(master['ticker'] == 'SPX', master['strike'] / 10.0, master['strike'])
    
    return master

def analyze_persistence(df):
    """
    Analyzes Position Persistence: OI Delta, Ghost, Fortress, VWAP.
    """
    if df.empty: return pd.DataFrame()
    
    # Group by Ticker, Strike, Expiry, Date
    daily_stats = df.groupby(['ticker', 'strike', 'expiry', 'date']).agg({
        'oi': 'max', 
        'vol': 'max', 
        'premium': 'max', 
        'is_bull': 'mean' 
    }).reset_index()
    
    daily_stats.sort_values(['ticker', 'strike', 'expiry', 'date'], inplace=True)
    
    # Calculate OI Delta
    daily_stats['prev_oi'] = daily_stats.groupby(['ticker', 'strike', 'expiry'])['oi'].shift(1)
    daily_stats['oi_delta'] = daily_stats['oi'] - daily_stats['prev_oi']
    daily_stats['oi_delta'] = daily_stats['oi_delta'].fillna(0)
    
    # VWAP Calculation 
    daily_stats['avg_price'] = daily_stats['premium'] / daily_stats['vol'].replace(0, 1)
    daily_stats['is_ghost'] = (daily_stats['vol'] > 1000) & (daily_stats['oi_delta'] <= 0)
    
    # Fortress Detector
    daily_stats['oi_inc'] = daily_stats['oi_delta'] > 0
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

def _global_get_orats(endpoint_type, ticker_arg='SPY', log_func=print):
    url = f"https://api.orats.io/datav2/live/{endpoint_type}"
    params = {
        'token': ORATS_API_KEY.strip(), 
        'ticker': ticker_arg,
        'fields': 'ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBidPrice,callAskPrice,putBidPrice,putAskPrice'
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 429:
            log_func(f"⚠️ ORATS Rate Limit ({endpoint_type}).")
            return None
        r.raise_for_status()
        data = r.json()
        res = data.get('data', data)
        return res if res else None
    except Exception as e:
        log_func(f"ORATS Error: {e}")
        return None

def run_snapshot_cycle(log_func=print, last_spot_price=600.0):
    """
    Standalone fetcher for Headless & TUI modes.
    """
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        TICKER_EQUITY = "SPY"
        
        # 1. FETCH STRIKES
        fetch_targets = [('SPY', 'snapshots_spy'), ('SPX', 'snapshots')]
        
        for ticker_req, folder_name in fetch_targets:
            log_func(f"⬇️ Fetching {ticker_req} Data (ORATS)...")
            orats_strikes = _global_get_orats('strikes', ticker_arg=ticker_req, log_func=log_func)
        
            if orats_strikes:
                spy_rows = []
                current_price = last_spot_price if last_spot_price > 0 else 600.0
                
                for item in orats_strikes:
                    # If we only have SPY spot price, infer SPX Spot price as SPY * 10
                    # Fallback to avoid poisoning SPX files with SPY prices
                    use_price = current_price
                    if ticker_req == 'SPX' and current_price < 2000 and current_price > 10:
                        use_price = (current_price * 10.0) + 30.0

                    base_data = {
                        'symbol': ticker_req, 
                        'exp': item.get('expirDate'),
                        'dte': item.get('dte'),
                        'stk': item.get('strike'),
                        'underlying_price': use_price
                    }
                    
                    c_delta = float(item.get('callDelta') or item.get('delta') or 0)
                    p_delta = float(item.get('putDelta') or 0)
                    c_gamma = float(item.get('callGamma') or item.get('gamma') or 0)
                    p_gamma = float(item.get('putGamma') or item.get('gamma') or 0)
                    c_vega = float(item.get('callVega') or item.get('vega') or 0)
                    p_vega = float(item.get('putVega') or item.get('vega') or 0)
                    c_theta = float(item.get('callTheta') or item.get('theta') or 0)
                    p_theta = float(item.get('putTheta') or item.get('theta') or 0)

                    iv_val = float(item.get('smvVol') or 0)
                    if (c_theta == 0 or c_vega == 0) and iv_val > 0:
                        try:
                            import mibian
                            try:
                                dte_days = (pd.to_datetime(item.get('expirDate')) - pd.Timestamp.now()).days
                                if dte_days < 0.01: dte_days = 0.01
                            except: dte_days = 1.0
                            
                            bs = mibian.BS([current_price, float(item.get('strike')), 0, dte_days], volatility=iv_val * 100)
                            
                            c_theta = float(item.get('callTheta') or item.get('theta') or 0) * 100
                            c_vega  = float(item.get('callVega') or item.get('vega') or 0) * 100
                            c_gamma = float(item.get('callGamma') or item.get('gamma') or 0) * 100
                            c_delta = float(item.get('callDelta') or item.get('delta') or 0)

                            p_theta = float(item.get('putTheta') or item.get('theta') or 0) * 100
                            p_vega  = float(item.get('putVega') or item.get('vega') or 0) * 100
                            p_gamma = float(item.get('putGamma') or item.get('gamma') or 0) * 100
                            p_delta = float(item.get('putDelta') or 0)
                            
                            if c_theta == 0: c_theta = bs.callTheta * 100
                            if c_vega == 0:  c_vega = bs.vega * 100
                            if c_gamma == 0: c_gamma = bs.gamma * 100
                            
                            if p_theta == 0: p_theta = bs.putTheta * 100
                            if p_vega == 0:  p_vega = bs.vega * 100
                            if p_gamma == 0: p_gamma = bs.gamma * 100

                            if c_delta == 0: c_delta = bs.callDelta
                            if p_delta == 0: p_delta = bs.putDelta
                            
                        except: pass
                    
                    if p_delta == 0 and c_delta != 0: p_delta = c_delta - 1.0

                    c_row = base_data.copy()
                    c_row.update({ 'type': 'CALL', 'vol': item.get('callVolume', 0), 'oi': item.get('callOpenInterest', 0), 'delta': c_delta, 'gamma': c_gamma, 'vega': c_vega, 'theta': c_theta, 'prem': 0 })
                    try:
                        mid = (item.get('callBidPrice', 0) + item.get('callAskPrice', 0)) / 2
                        c_row['prem'] = mid * c_row['vol'] * 100
                    except: pass
                    spy_rows.append(c_row)
                    
                    p_row = base_data.copy()
                    p_row.update({ 'type': 'PUT', 'vol': item.get('putVolume', 0), 'oi': item.get('putOpenInterest', 0), 'delta': p_delta, 'gamma': p_gamma, 'vega': p_vega, 'theta': p_theta, 'prem': 0 })
                    try:
                        mid = (item.get('putBidPrice', 0) + item.get('putAskPrice', 0)) / 2
                        p_row['prem'] = mid * p_row['vol'] * 100
                    except: pass
                    spy_rows.append(p_row)

                if spy_rows:
                    df_out = pd.DataFrame(spy_rows)
                    os.makedirs(folder_name, exist_ok=True)
                    t_lower = ticker_req.lower()
                    df_out.to_csv(f"{folder_name}/{t_lower}_snapshot_{timestamp}.csv", index=False)
                    log_func(f"✅ Saved {ticker_req} Snapshot: {len(df_out)} rows")
            else:
                log_func(f"⚠️ {ticker_req} Fetch Failed (Empty).")

        # 2. STAGGER -> REFRESH COMPLETE
        time.sleep(2)

    except Exception as e:
        log_func(f"❌ FETCH ERROR: {e}")
        # traceback.print_exc()

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
    precise_spx = reactive(0.0) # [NEW] Track SPX Logic

    def compose(self) -> ComposeResult:
        with Container(id="header-container"):
            with Horizontal():
                yield Label("Strategic Narrative:", classes="lbl")
                yield Static("Loading Narrative...", id="narrative-box")
            with Horizontal():
                yield Label("Market Regime:", classes="lbl")
                yield Label("ANALYZING...", id="regime-lbl", classes="val")
                
                # [NEW] Price Header
                yield Label("| SPX:", classes="lbl")
                yield Label("Loading...", id="spx-price-lbl", classes="val")
                yield Label("| SPY:", classes="lbl")
                yield Label("Loading...", id="spy-price-lbl", classes="val")
                
                yield Label("| RVOL:", classes="lbl")
                yield Label("Loading...", id="rvol-lbl", classes="val")
                
                yield Label("| Div:", classes="lbl")
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
        self.last_spot_update_ts = 0.0 # [FIX] Initialize timestamp
        # Setup Heatmap
        # Heatmap Removed
        # dt_hm = self.query_one("#dt_heatmap", DataTable)
        # dt_hm.add_columns("STRIKE", "D-5", "D-4", "D-3", "D-2", "D-1", "TODAY", "TOTAL Δ")
        
        # Setup Kill Box SPX (Gold Headers)
        dt_spx = self.query_one("#dt_kill_spx", DataTable)
        dt_spx.cursor_type = "row"
        dt_spx.add_columns(
            Text("STRIKE", style="bold gold"), 
            Text("DTE", style="bold gold"),     # RESTORED
            Text("DIST%", style="bold gold"),   # Fuse
            Text("IMPACT", style="bold gold"),  # Visual Bar
            Text("NET Δ", style="bold gold"),
            Text("STATUS", style="bold gold"), 
            Text("PANIC", style="bold red"),
        )
        
        # Setup Kill Box SPY (Cyan Headers)
        dt_spy = self.query_one("#dt_kill_spy", DataTable)
        dt_spy.cursor_type = "row"
        dt_spy.add_columns(
            Text("STRIKE", style="bold cyan"), 
            Text("DTE", style="bold cyan"),     # RESTORED
            Text("DIST%", style="bold cyan"),   # Fuse
            Text("IMPACT", style="bold cyan"),  # Visual Bar
            Text("NET Δ", style="bold cyan"),
            Text("STATUS", style="bold cyan"), 
            Text("PANIC", style="bold red"),
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

        # [FIX] Automatically Refresh Analysis (and JSON payload) every 30 seconds
        self.set_interval(30.0, self.refresh_analysis)
        self.set_interval(3600.0, self.on_hourly_fetch) # HOURLY FETCH TRIGGER

        
        # Start Nexus Feed
        self.run_worker(self.sub_nexus_feed)
        
        # Start API Fallback (for closed markets)
        self.run_worker(self.fetch_fallback_price)
        
        # [FIX] Force Data Refresh on Startup
        # This ensures we don't load stale data if the script was just restarted.
        # Run in thread because fetch_and_save_snapshots uses blocking requests.
        self.run_worker(self.fetch_and_save_snapshots, thread=True)

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
        """
        [REFACTORED] Sends alert via ZMQ Fire-and-Forget Protocol.
        Isolates Logic Layer from Discord/Network failures (Section 10).
        """
        try:
            # Global 'sock_notify' is initialized at module level (Line 48)
            # We access it directly. 
            if 'sock_notify' in globals() and sock_notify:
                payload = {
                    "title": title,
                    "message": body,
                    "color": color,
                    "topic": "SENTINEL_HUD" # Optional: Keeps HUD updates clean if we ever want to edit
                }
                sock_notify.send_json(payload, flags=zmq.NOBLOCK)
                self.log_msg(f"SENTINEL (ZMQ): {title}")
            else:
                self.log_msg("SENTINEL: Notification Socket Not Connected.")
                
        except Exception as e:
            # CRITICAL FAIL-SAFE: Never crash the math loop for a message
            self.log_msg(f"SENTINEL NOTIFICATION ERR: {e}")

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
        """Wrapper for Global Engine"""
        run_snapshot_cycle(log_func=self.write_log, last_spot_price=self.last_spot_price)
        # Old code removed.

    def get_orats_data(self, endpoint_type, ticker_arg='SPY'):
        api_url = f"https://api.orats.io/datav2/live/{endpoint_type}"
        # Request FULL fields (Corrected Names)
        params = {
            'token': ORATS_API_KEY.strip(), 
            'ticker': ticker_arg,
            'fields': 'ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBidPrice,callAskPrice,putBidPrice,putAskPrice'
        }
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
            # Fix: load_unified_data(0) to exclude corrupted history from yesterday.
            # We only want fresh, valid data in the UI right now.
            today_df = await loop.run_in_executor(None, load_unified_data, 0, None)
            
            if not today_df.empty:
                self.current_df = today_df
                try:
                    with open("/root/loader_debug.log", "a") as lf: lf.write("STARTING PERSISTENCE ANALYSIS...\n")
                except: pass
                
                self.daily_stats = analyze_persistence(today_df)
                
                try:
                    with open("/root/loader_debug.log", "a") as lf: lf.write("PERSISTENCE DONE.\n")
                except: pass
                
                self.log_msg("✅ Persistence Analyzed.")
                
                # Update Active Traps IMMEDIATELY
                live_spy = self.last_spot_price
                live_spx = live_spy * 10.03 
                
                # [FIX] Read Precise SPX Price from Profiler
                try:
                    import json
                    if os.path.exists("nexus_spx_profile.json"):
                        with open("nexus_spx_profile.json", "r") as f:
                            profile_data = json.load(f)
                            if profile_data.get('spx_price', 0) > 0:
                                live_spx = float(profile_data['spx_price'])
                                self.precise_spx = live_spx # Store for later
                                self.log_msg(f"🎯 Precise SPX Check: ${live_spx:.2f}")
                except Exception as e:
                     self.log_msg(f"⚠️ Failed to read SPX Profile: {e}")

                if 'underlying_price' in today_df.columns and live_spx == (live_spy * 10.03):
                     spx_rows = today_df[today_df['ticker'] == 'SPX']
                     if not spx_rows.empty:
                         last_spx = spx_rows['underlying_price'].iloc[-1]
                         if last_spx > 0 and abs(last_spx - (live_spy*10)) < 100: 
                            live_spx = float(last_spx)
                            self.precise_spx = live_spx 

                # UPDATE HEADER LABELS (FAST)
                try:
                    self.query_one("#spx-price-lbl", Label).update(f"${live_spx:,.2f}")
                    self.query_one("#spy-price-lbl", Label).update(f"${live_spy:,.2f}")

                    # [NEW] RVOL UPDATE
                    if os.path.exists("nexus_structure.json"):
                         with open("nexus_structure.json", 'r') as f: 
                             struct_data = json.load(f)
                             rvol = struct_data.get("SPY", {}).get("trend_metrics", {}).get("rvol", 0)
                             hrvol = struct_data.get("SPY", {}).get("trend_metrics", {}).get("hourly_rvol", 0)
                             
                             r_lbl = self.query_one("#rvol-lbl", Label)
                             r_val = f"D:{rvol:.1f}x H:{hrvol:.1f}x"
                             r_lbl.update(r_val)
                             
                             if hrvol > 2.0: r_lbl.styles.color = "#00ff00"
                             elif hrvol > 1.5: r_lbl.styles.color = "yellow"
                             elif hrvol < 0.8: r_lbl.styles.color = "#444444"
                             else: r_lbl.styles.color = "white"
                except: pass
                
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
            self.log_msg("⏳ Loading 5-Day History in Background...")
            loop = asyncio.get_event_loop()
            full_df = await loop.run_in_executor(None, load_unified_data, 5, None)
            
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
            
            # --- BEGIN DASHBOARD SYNC INJECTION ---
            try:
                # 3. Calculate Trend Signals
                total_oi_delta = self.daily_stats['oi_delta'].sum()
                
                total_prem = full_df['premium'].sum()
                bull_prem = full_df[full_df['is_bull']]['premium'].sum()
                sentiment_score = (bull_prem / total_prem * 100) if total_prem > 0 else 50
                
                net_flow = full_df[full_df['is_bull']]['premium'].sum() - full_df[~full_df['is_bull']]['premium'].sum()
                
                level_stats = self.daily_stats.groupby('strike')['oi_delta'].sum().sort_values(ascending=False)
                major_support = level_stats.head(1).index[0] if not level_stats.empty else 0
                major_resistance = level_stats.tail(1).index[0] if not level_stats.empty else 0
                
                # Cold Start Logic
                unique_dates = sorted(list(set([d.strftime('%Y-%m-%d') for d in full_df['date'] if pd.notnull(d)])))
                days_count = len(unique_dates)
                trend_label = f"{days_count}-Day Trend"
                if days_count < 2:
                    trend_status = "INSUFFICIENT_DATA"
                    flow_dir = "UNKNOWN"
                else:
                    trend_status = "ACCUMULATION" if total_oi_delta > 0 else "DISTRIBUTION"
                    flow_dir = "BULLISH_TREND" if net_flow > 0 else "BEARISH_TREND"

                struct_metrics = calculate_market_structure_metrics(full_df, self.last_spot_price)
                trajectory = calculate_trajectory_logic(self.last_spot_price, struct_metrics['flow_pain'], struct_metrics['top_gex'], full_df, struct_metrics.get('volume_poc', 0))
                divergence = check_divergence_logic(self.daily_stats, sentiment_score)

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
                        "trajectory": trajectory,
                        "divergence": divergence,
                        "flow_pain": struct_metrics['flow_pain']
                    },
                    "persistent_levels": {
                        "major_support": major_support,
                        "major_resistance": major_resistance
                    },
                    "structural_magnets": struct_metrics.get('top_gex_details', []),
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                antigravity_dump("nexus_history.json", history_state)
            except Exception as e:
                self.log_msg(f"Dashboard Sync Error: {e}")
            # --- END DASHBOARD SYNC INJECTION ---
            
            # Re-run Traps just in case history changed context (Fortress checks etc)
            # But we keep the live prices we already have
            live_spy = self.last_spot_price
            
            # [FIX] Use Precise SPX if we have it
            if self.precise_spx > 0:
                live_spx = self.precise_spx
            else:
                live_spx = live_spy * 10.03

            # Update Header Again
            try:
                self.query_one("#spx-price-lbl", Label).update(f"${live_spx:,.2f}")
                self.query_one("#spy-price-lbl", Label).update(f"${live_spy:,.2f}")
            except: pass

            try:
                with open("/root/loader_debug.log", "a") as lf: lf.write("BUILDING KILL BOX...\n")
            except: pass
            
            await self.build_kill_box(live_spx=live_spx, live_spy=live_spy)
            
            try:
                with open("/root/loader_debug.log", "a") as lf: lf.write("KILL BOX BUILT.\n")
            except: pass
            
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
        # [FIX] NO HARDCODED FALLBACK. Derive from Data if Live Feed is Silent.
        
        derived_spot = 0.0
        if 'underlying_price' in self.current_df.columns:
            # FIX: Only look at rows that are ACTUALLY SPY and have VALID price
            spy_rows = self.current_df[
                (self.current_df['ticker'] == 'SPY') & 
                (self.current_df['underlying_price'] > 610.0)
            ]
            if not spy_rows.empty:
                # Use the most recent valid price
                derived_spot = float(spy_rows['underlying_price'].iloc[-1])
                # Double Safety: If derived spot is 600.0 (the known SPX garbage value), ignore it
                if abs(derived_spot - 600.0) < 1.0:
                     derived_spot = 0.0

        SPY_PRICE = live_spy if live_spy > 0 else (self.last_spot_price if self.last_spot_price > 0 else derived_spot)
        
        # SPX: Use arg, or derive
        SPX_PRICE = live_spx if live_spx > 0 else (SPY_PRICE * 10.03)

        # [FALLBACK] If SPY is still dead but SPX is alive, infer SPY
        if SPY_PRICE <= 10.0 and SPX_PRICE > 2000.0:
             SPY_PRICE = SPX_PRICE / 10.0
             try:
                 with open("/root/loader_debug.log", "a") as lf: lf.write(f"  -> SPY Price inferred from SPX: {SPY_PRICE}\n")
             except: pass
        
        if SPY_PRICE == 0:
            SPY_PRICE = 685.0 # Prevent hard total failure 
            self.log_msg("⚠️ CRITICAL: No Spot Price available. Defaulting to safe floor ($685.0).")
        else:
            self.log_msg(f"🔎 Kill Box Context: Spot=${SPY_PRICE:.2f} (Source: {'Live' if live_spy>0 else 'Data'})")

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
            
            # Filter Extreme OTM
            eff_spx = SPX_PRICE if SPX_PRICE > 2000 else (SPY_PRICE * 10.0)
            eff_spy = SPY_PRICE

            cond_spx = (active_df['ticker'] == 'SPX') & (active_df['strike'].between(eff_spx * 0.95, eff_spx * 1.05))
            cond_spy = (active_df['ticker'] == 'SPY') & (active_df['strike'].between(SPY_PRICE * 0.95, SPY_PRICE * 1.05))
            
            merged = active_df[cond_spx | cond_spy].copy()           
            # Rule 1: Gamma Horizon (DTE <= 45 OR Premium > $100M)
            # 100M on SPX = a lot. 'premium' in active_df is per row.
            # We filter source rows first? Or aggregate then filter?
            # Better to filter source rows for DTE.
            # Premium > 100M check needs aggregation, but we can do a rough pass or do it after grouping.
            # User rule: "If DTE > 45: DELETE. Exception: massive block >$100M"
            
            # Let's filter by Strike first (Zone), then DTE.
            active_df = active_df[cond_spx | cond_spy]
            
            # Gamma Horizon PASS 1 (Simple DTE)
            # We will handle the "$100M Exception" AFTER aggregation because we need to sum premium per strike/expiry.

            
        except:
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

        merged = pd.concat([calls, puts], ignore_index=True)
        
        # --- RULE 1: GAMMA HORIZON (Updated Logic) ---
        # Exclude DTE > 14 UNLESS Gamma > 0.05
        # HARD CAP: DTE > 60 always deleted.
        
        def filter_gamma_horizon(row):
            if row['dte'] > 60: return False
            
            if row['dte'] <= 14: return True
            
            # Exception: High Gamma for 14 < DTE <= 60
            if row['gamma'] > 0.05: return True
            
            # Legacy Exception: Massive Premium (Keep for safety)
            if row['premium'] >= 100_000_000: return True
            
            return False
            
        merged = merged[merged.apply(filter_gamma_horizon, axis=1)]

        # --- SCORE: PANIC VELOCITY ---
        # (Gamma * 100) + Abs(Theta)
        # Identify urgent pressure.
        merged['panic_score'] = (merged['gamma'] * 100) + merged['theta'].abs()


        trapped = merged[merged['status'].str.contains("TRAPPED")].copy()
        
        if trapped.empty:
             # Create empty cols to prevent apply error if no traps
             trapped['notional_delta'] = 0.0
             trapped['weighted_impact'] = 0.0
             trapped['is_mega_whale'] = False
        # --- RULE 3: WHALE GRAVITY WEIGHTING ---
        # Replaced Hard $5M Filter with Weighted Sort
        
        
        # --- DEFINE HELPER FUNCTIONS FIRST ---

        def calc_gravity(row):
            # 1. Calc Notional Delta
            spot = SPX_PRICE if row['ticker'] == 'SPX' else SPY_PRICE
            nd = abs(row['oi_delta'] * spot)
            
            # 2. Calc Weighted Impact
            raw_score = row['panic_score']
            
            if nd < 500_000: 
                impact = raw_score * 0.1 # Noise Penalty
            else:
                impact = raw_score * 1.0 # Full Signal
                
            return pd.Series([nd, impact, nd > 2_000_000])

        def calc_days_left(row):
            burn = abs(row['theta'])
            if burn < 0.01: return 999.0
            price = row['avg_prem']
            if price <= 0.001: return 999.0
            return price / burn

        def enhance_status(row):
            s = row['status']
            score = row['panic_score']
            
            # Context Injection
            if score > 10.0:
                if "TRAPPED BEARS" in s: return f"🚀 ROCKET FUEL"
                if "TRAPPED BULLS" in s: return f"🛑 RESISTANCE"
            
            if row['days_left'] < 2.0: return f"💀 LIQUIDATION"
            if row['days_left'] < 5.0: return f"🔥 BURNING"
            return s

        # --- APPLY CALCULATIONS ---

        # 1. Trapped DF (Top Filter) - Legacy Calculation (Can be optimized to use Merged later)
        # Keeping this for safety to match original logic flow
        # 1. Trapped DF (Top Filter)
        if not trapped.empty:
            res = trapped.apply(calc_gravity, axis=1, result_type='expand')
            trapped['notional_delta'] = res[0]
            trapped['weighted_impact'] = res[1]
            trapped['is_mega_whale'] = res[2]
        else:
            trapped['notional_delta'] = 0.0
            trapped['weighted_impact'] = 0.0
            trapped['is_mega_whale'] = False
        trapped['days_left'] = trapped.apply(calc_days_left, axis=1)
        trapped['display_status'] = trapped.apply(enhance_status, axis=1)

        # 2. Merged DF (Total Market Context) - Used for Sheets Export
        # 2. Merged DF (Total Market Context)
        if not merged.empty:
            res_m = merged.apply(calc_gravity, axis=1, result_type='expand')
            merged['notional_delta'] = res_m[0]
            merged['weighted_impact'] = res_m[1]
            merged['is_mega_whale'] = res_m[2]
        else:
            merged['notional_delta'] = 0.0
            merged['weighted_impact'] = 0.0
            merged['is_mega_whale'] = False
        merged['days_left'] = merged.apply(calc_days_left, axis=1)
        merged['display_status'] = merged.apply(enhance_status, axis=1)

        # Re-Filter Trapped based on Enhanced Status (Rocket Fuel/Burning/etc)
        # trapped = merged[merged['display_status'].str.contains("TRAPPED") | merged['display_status'].str.contains("LIQUIDATION") | merged['display_status'].str.contains("BURNING")].copy()
        # NOTE: The original logic filtered 'trapped' early. Let's keep 'trapped' as the primary visualization subset.

        
        if trapped.empty:
            merged['display_status'] = "SUPPORT/RESIST"
            merged['days_left'] = 999
            trapped = merged.sort_values('oi', ascending=False).head(50)
        
        # --- PRIORITY SORT LOGIC ---
        # 1. Force Include ATM Strikes (Zone +/- $3.00)
        # Even if they have low impact, we need to see them for context.
        spot_spy = SPY_PRICE
        spot_spx = SPX_PRICE
        
        def calc_priority_score(row):
            # Base Score = Weighted Impact
            score = row['weighted_impact']
            
            # ATM Bonus (make them sticky)
            this_spot = spot_spx if row['ticker'] == 'SPX' else spot_spy
            dist = abs(row['strike'] - this_spot)
            
            # SPY ATM Zone +/- 2.00
            if row['ticker'] == 'SPY' and dist < 2.0:
                score += 1000.0 # Force into top list
                
            # SPX ATM Zone +/- 12.00
            if row['ticker'] == 'SPX' and dist < 12.0:
                score += 1000.0
                
            if row['is_mega_whale']:
                score += 500.0
                
            return score

        trapped['priority_score'] = trapped.apply(calc_priority_score, axis=1)

        # Sort by Priority Score and take Top 50 (Increased from 20)
        spx_traps = trapped[trapped['ticker'] == 'SPX'].sort_values(by='priority_score', ascending=False).head(50)
        spy_traps = trapped[trapped['ticker'] == 'SPY'].sort_values(by='priority_score', ascending=False).head(50)
        
        # --- NEW: DISPLAY SORT (LADDER VIEW) ---
        # Re-sort the Top 50 by Strike Price to create a visual "Kill Box" Map
        spx_traps = spx_traps.sort_values(by='strike', ascending=False)
        spy_traps = spy_traps.sort_values(by='strike', ascending=False)

        self.log_msg("Visualizing magnitude and proximity. High-impact structural walls and immediate break risks are now optically highlighted.")

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
            
            # Pre-calculate Max Notional for this group to scale visual bars
            group_max_nd = data['notional_delta'].abs().max() if not data.empty else 1_000_000
            if group_max_nd == 0: group_max_nd = 1

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

                
                # Delta Style (SWITCHED TO NOTIONAL DOLLARS)
                d_val = row['notional_delta']
                d_str = fmt_notional(d_val, show_plus=False)
                if d_val >= 2_000_000: d_str = f"🐳 {d_str}" # Mega Whale Icon
                d_style = "bold green" if row['oi_delta'] > 0 else "bold red"
                
                # --- DANGER MAP: IMPACT BARS ---
                # Scale 1-10 based on relative size to the biggest whale in the list
                bars = int((abs(d_val) / group_max_nd) * 10)
                bars = max(1, min(10, bars))
                impact_bar = "█" * bars
                bar_style = "green" if row['oi_delta'] > 0 else "red"

                # --- DANGER MAP: PROXIMITY FUSE ---
                spot_price = SPX_PRICE if row['ticker'] == 'SPX' else SPY_PRICE
                if spot_price <= 0: spot_price = 1.0 # Prevent DivByZero
                dist_pct = abs(spot_price - row['strike']) / spot_price * 100
                
                fuse_style = "dim white"
                if dist_pct < 0.3: fuse_style = "bold white on red" # DANGER ZONE
                elif dist_pct < 0.6: fuse_style = "bold yellow"     # WARNING ZONE
                
                dist_str = f"{dist_pct:.2f}%"

                # Panic Style
                p_val = row.get('panic_score', 0)
                p_txt = f"{p_val:.1f}"
                if p_val > 10: p_txt += " 🔥"
                p_style = "bold yellow" if p_val > 10 else "dim white"

                # Layout: STRIKE | DIST% | IMPACT | NET Δ | STATUS | PANIC
                
                # Safe Strike Formatting & SPX Conversion
                strk_val = float(row['strike'])
                strk_txt = f"{strk_val:.0f}" if strk_val.is_integer() else f"{strk_val:.1f}"
                
                # If SPX, append [SPY Equivalent] using Basis
                if row['ticker'] == 'SPX':
                    if SPX_PRICE > 0 and SPY_PRICE > 0:
                        basis = SPX_PRICE - (SPY_PRICE * 10)
                        spy_eq = (strk_val - basis) / 10.0
                    else:
                        spy_eq = strk_val / 10.0 # Fallback
                    strk_txt += f" [{spy_eq:.1f}]"

                dt.add_row(
                    Text(strk_txt, style="bold white"),
                    Text(f"{row['dte']:.0f}d", style="white"), # New DTE Col
                    Text(dist_str, style=fuse_style),
                    Text(impact_bar, style=bar_style),
                    Text(d_str, style=d_style),
                    Text(s_txt, style=s_style),
                    Text(p_txt, style=p_style),
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

             
             # --- NEW: EXPORT WALL CONTEXT FOR SHEETS (ALL STRIKES - UNFILTERED) ---
             # [FIX] Use active_df (Superset) instead of merged (Filtered) to ensure we capture ALL walls.
             # We must perform the minimal calculations needed for context (Delta, IO Delta)
             
             try:
                 ctx_df = active_df.copy()
                 
                 # Ensure 0s for missing cols
                 for c in ['oi', 'delta', 'gamma', 'theta', 'premium', 'vol']:
                      if c not in ctx_df.columns: ctx_df[c] = 0.0

                 # Calc Delta/Gravity
                 def fast_ctx_calc(row):
                     spot = SPX_PRICE if row['ticker'] == 'SPX' else SPY_PRICE
                     # OI Delta
                     # We need previous OI? active_df might not have it if we didn't run persistence.
                     # persistence runs on 'today_df' or 'full_df'. active_df comes from current_df.
                     # 'daily_stats' has oi_delta.
                     # Optim: Just use current OI * Delta for "Notional Delta Exposure" (which is what we really want for Wall Power)
                     # Wait, user wants "Rolling Net Delta"?
                     # If we don't have oi_delta in active_df, we use OI.
                     # But 'analyze_persistence' adds 'oi_delta'. 
                     # Let's check if 'oi_delta' is in active_df columns.
                     
                     oid = row.get('oi_delta', 0)
                     nd = abs(oid * spot)
                     return pd.Series([nd, oid])

                 # If oi_delta is missing (e.g. Day 1 load), use OI? No, OI Delta is change.
                 # If missing, it's 0.
                 if 'oi_delta' not in ctx_df.columns:
                      # Try to merge from daily_stats?
                      # daily_stats has ticker, strike, expiry.
                      # This is getting complex for a quick fix.
                      # Alternative: Just use 'active_df' which is a slice of 'current_df'.
                      # Does 'current_df' have 'oi_delta'? No, it's in 'daily_stats'.
                      pass

                 # RE-MERGE daily_stats to get oi_delta if needed?
                 # Actually, 'analyze_persistence' returns 'daily_stats'. 'current_df' is raw rows.
                 # We should use 'self.daily_stats' as the source! It has 'oi_delta'.
                 
                 ctx_source = self.daily_stats.copy()
                 
                 # Filter for Today
                 # daily_stats has multiple days? No, 'analyze_persistence' groups by date.
                 # We want the LATEST date for each contract.
                 ctx_source = ctx_source.sort_values('date').groupby(['ticker', 'strike', 'expiry']).tail(1)
                 
                 
                 # Calc Notional PER ROW first
                 # [FIX] Use TOTAL OI (Position Strength) instead of OI Delta (Flow). 
                 # This ensures we see the Wall size even if no flow occurred today.
                 # Formula: OI * 100 * OptionDelta * SpotPrice
                 def calc_total_notional(r):
                     spot = SPX_PRICE if r['ticker']=='SPX' else SPY_PRICE
                     # Delta from snapshot (0.0 - 1.0)
                     d = r.get('delta', 0)
                     oi = r.get('oi', 0)
                     return abs(oi * 100 * d * spot)

                 ctx_source['notional_delta'] = ctx_source.apply(calc_total_notional, axis=1)
                 
                 # [NEW] Load Verified Chain Data (True OI/Delta)
                 # [FIX] Aggregate across ALL expirations (don't overwrite keys)
                 verified_chain_agg = {}
                 try:
                     if os.path.exists("nexus_gex_chain.json"):
                        with open("nexus_gex_chain.json", "r") as f:
                            raw_chain = json.load(f)
                            
                            # Pre-calculate Spot once (fallback)
                            spot_ref = SPX_PRICE if SPX_PRICE > 0 else 6900
                            
                            for item in raw_chain:
                                try:
                                    k = f"{item['strike']:.1f}"
                                    
                                    # Calc Row Notional Delta
                                    total_oi = item.get('call_oi', 0) + item.get('put_oi', 0)
                                    delta_val = abs(float(item.get('delta', 0))) # Use provided delta
                                    
                                    # Notional Delta = OI * 100 * Spot * Delta
                                    row_nd = total_oi * 100 * spot_ref * delta_val
                                    
                                    # Aggregate
                                    if k not in verified_chain_agg: verified_chain_agg[k] = 0.0
                                    verified_chain_agg[k] += row_nd
                                except: pass
                                
                        self.log_msg(f"✅ Loaded Verified Chain: {len(verified_chain_agg)} unique strikes (Aggregated)")
                 except Exception as e:
                     self.log_msg(f"⚠️ Chain Load Error: {e}")

                 valid_walls = {}
                 for tick in ["SPX", "SPY"]:

                     valid_walls[tick] = {}
                     subset = ctx_source[ctx_source['ticker'] == tick]
                     
                     # Group by Strike
                     agg_subset = subset.groupby('strike')['notional_delta'].sum().reset_index()
                     
                     for _, row in agg_subset.iterrows():
                         k = str(float(row['strike']))
                         
                         # Use current calculation as baseline
                         n_delta = row['notional_delta']

                         # [OVERRIDE] If SPX, Check Verified Chain for Source of Truth
                         if tick == "SPX" and k in verified_chain_agg:
                             # Use the pre-aggregated value
                             n_delta = verified_chain_agg[k]
                         
                         valid_walls[tick][k] = {
                             "delta": n_delta,
                             "oi_delta": 0, 
                             "status": "ACTIVE" 
                         }


                 self.log_msg("✅ Walls Context Processed (Internal Tracker Updated).")

             except Exception as e:
                 self.log_msg(f"⚠️ Context Export Error: {e}")
             # -------------------------------------------

             
        except Exception as e:
             self.log_msg(f"⚠️ Quant/Wall Bridge Failed: {e}")

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
        self.last_magnet = metrics.get('volume_poc', 0)
        
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
            self.log_msg(f"[WARN] Failed to load structure data: {e}")
        # -----------------------------
        
        # Populate UI
        if self.last_flow_pain > 0:
            dt.add_row("FLOW PAIN", f"${self.last_flow_pain:.2f}", "Todays Trader Pain Lvl")
        else:
            dt.add_row("WARNING", "NO GAMMA DATA", "GEX calc impossible")

        # [FIX] Use DETAILS list with Expiry Info
        top_details = metrics.get('top_gex_details', [])
        
        # Fallback if details missing (rare)
        if not top_details and not self.last_top_gex.empty:
             for k, v in self.last_top_gex.items():
                 top_details.append({'strike': k, 'gex': v, 'expiry': 'N/A'})
                 
        for item in top_details:
            k = item['strike']
            v = item['gex']
            exp = item['expiry']
            
            # [FIX] Smart Currency Formatting (B vs M)
            abs_v = abs(v)
            if abs_v >= 1e9:
                fmt_v = f"${v/1e9:.2f}B"
            else:
                fmt_v = f"${v/1e6:.1f}M"
            
            # [FIX] Contextual Labels
            if v > 0:
                tag = "POS GEX (+)"
                desc = f"Magnet/Support (Exp: {exp})"
            else:
                tag = "NEG GEX (-)"
                desc = f"Vol Trigger/Accel (Exp: {exp})"
            
            # Visualize Magnitude
            label = f"MAGNET {tag}"
            dt.add_row(label, f"${k:.2f}", f"{fmt_v} Net Gamma ({desc})")

    def calculate_trajectory(self):
        spot = self.last_spot_price
        pain = getattr(self, 'last_flow_pain', 0)
        top_gex = getattr(self, 'last_top_gex', pd.Series(dtype=float))
        magnet = getattr(self, 'last_magnet', 0)
        
        return calculate_trajectory_logic(spot, pain, top_gex, self.current_df, magnet)

    def check_divergence(self):
        div_detected = check_divergence_logic(self.daily_stats, self.sentiment_score)
        
        if div_detected:
            self.divergence_alert = div_detected
            self.query_one("#div-lbl", Label).update(div_detected)
            self.query_one("#div-lbl", Label).styles.color = "green" if "BULL" in div_detected else "red"
            
            # Border Alert
            color = "green" if "BULL" in div_detected else "red"
            self.screen.styles.border = ("heavy", color)
            self.log_msg(f"[CRITICAL] MARKET DIVERGENCE DETECTED: {div_detected}")
        else:
            self.divergence_alert = None
            self.query_one("#div-lbl", Label).update("NONE")
            self.query_one("#div-lbl", Label).styles.color = "white"
            self.screen.styles.border = None

    def write_log(self, msg):
        # Write to file to ensure capture
        try:
            with open("/root/greeks_debug.log", "a") as f:
                f.write(f"[{get_now_str()}] {msg}\n")
        except:
             pass
        # Also print just in case
        print(f"[{get_now_str()}] {msg}")

    @on(Button.Pressed, "#btn_snapshot")
    def on_snapshot(self):
        # ... (Existing snapshot logic) ...
        pass

# --- STANDALONE LOGIC FUNCTIONS ---
def calculate_market_structure_metrics(df, spot_price):
    """Calculates Flow Pain and Top GEX Levels (With Expiry Context)."""
    results = {'flow_pain': 0, 'top_gex': pd.Series(dtype=float), 'top_gex_details': []}
    
    if df.empty: return results
    
    # Filter for SPY
    spy_df = df[df['ticker'] == 'SPY'].copy()
    if spy_df.empty: return results
    
    # [FIX] Isolate to current day to avoid summing 5 days of cumulative history
    if 'date' in spy_df.columns and not spy_df.empty:
        latest_date = spy_df['date'].max()
        spy_df = spy_df[spy_df['date'] == latest_date]

    # [FIX] FILTER EXPIRED OPTIONS
    try:
        now_ts = pd.Timestamp.now().normalize()
        if 'expiry' in spy_df.columns:
            spy_df['expiry_dt'] = pd.to_datetime(spy_df['expiry'], errors='coerce')
            
            # [FIX] Fallback to Date + DTE if expiry string parsing fails (prevents NaT wiping)
            mask_nat = spy_df['expiry_dt'].isna()
            if mask_nat.any() and 'date' in spy_df.columns and 'dte' in spy_df.columns:
                spy_df['date_ts'] = pd.to_datetime(spy_df['date'])
                spy_df.loc[mask_nat, 'expiry_dt'] = spy_df.loc[mask_nat, 'date_ts'] + pd.to_timedelta(spy_df.loc[mask_nat, 'dte'], unit='D')
            
            spy_df = spy_df[spy_df['expiry_dt'] >= now_ts]
            if spy_df.empty: return results
    except: pass

    # [FIX] Derive Valid Spot & Filter Outliers
    spot = spot_price
    if spot <= 0 and not spy_df.empty:
        # Try to infer spot from internal data if provided spot is dead
        if 'underlying_price' in spy_df.columns:
             valid_prices = spy_df[spy_df['underlying_price'] > 10.0]['underlying_price']
             if not valid_prices.empty: spot = valid_prices.iloc[-1]
    
    # Fallback to 690 if totally dead (better than 0 or 600)
    if spot <= 10: spot = 690.0

    # Filter spy_df to reasonable range (+/- 25%) to kill anomalies (like Strike 1000)
    spy_df = spy_df[spy_df['strike'].between(spot * 0.75, spot * 1.25)]

    # --- INDEPENDENT CALCULATION: VOLUME POC (Magnet) ---
    # Volume POC only requires 'vol' and should NOT be blocked if Gamma is missing.
    try:
        poc_df = spy_df.copy()
        if 'dte' in poc_df.columns:
            poc_df = poc_df[poc_df['dte'] <= 14]
        valid_range = spot * 0.10
        poc_df = poc_df[poc_df['strike'].between(spot - valid_range, spot + valid_range)]
        
        vol_profile = poc_df.groupby('strike')['vol'].sum()
        if not vol_profile.empty and vol_profile.max() > 0:
            results['volume_poc'] = vol_profile.idxmax()
        else:
            results['volume_poc'] = 0.0
    except:
        results['volume_poc'] = 0.0

    # --- INDEPENDENT CALCULATION: FLOW PAIN ---
    # Flow Pain models max pain relative to Volume (not Gamma), so it shouldn't be blocked.
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

    # 1. SAFETY CHECK: Missing Gamma (Blocks GEX & Traps)
    if 'gamma' not in spy_df.columns or spy_df['gamma'].sum() == 0:
         return results
    
    # 2. FLOW GEX CALCULATION
    spy_df['flow_gex'] = spy_df['gamma'] * spy_df['vol'] * spot * 100
    gex_profile = spy_df.groupby('strike')['flow_gex'].sum().sort_index()
    
    # 4. FLOW MAGNETS (With Expiry Context)
    results['top_gex'] = gex_profile.abs().nlargest(3)

    # [NEW] Calculate Dominant Expiry
    top_strikes = results['top_gex'].index
    details = []
    for k in top_strikes:
        total_gex = gex_profile[k]
        try:
            strike_slice = spy_df[spy_df['strike'] == k]
            if not strike_slice.empty:
                 # Find exp with most Absolute GEX contribution
                 # [MODIFIED] User requested 0DTE focus. Filter for today if present.
                 import datetime
                 today_str = datetime.datetime.now().strftime('%Y-%m-%d')
                 if today_str in strike_slice['expiry'].values:
                     dom_exp = today_str
                 else:
                     # Fallback to absolute heaviest expiry
                     dom_exp = strike_slice.groupby('expiry')['flow_gex'].apply(lambda x: x.abs().sum()).idxmax()
                 
                 # Format date nicely YYYY-MM-DD -> MM/DD
                 if isinstance(dom_exp, str) and len(dom_exp) >= 10:
                     dt_obj = pd.to_datetime(dom_exp)
                     dom_exp = dt_obj.strftime('%m/%d')
            else:
                 dom_exp = "N/A"
        except: dom_exp = "?"
        
        details.append({'strike': k, 'gex': total_gex, 'expiry': dom_exp})
        
    results['top_gex_details'] = details
    return results

def calculate_trajectory_logic(spot_price, flow_pain, top_gex, df, volume_poc=0):
    """Calculates Trajectory, Magnet, and Drift."""
    if spot_price == 0: return "WAITING FOR DATA"
    
    # 1. PRESSURE
    pressure = "NEUTRAL"
    if flow_pain > 0:
        if spot_price < flow_pain: pressure = "BEARISH DRAG (Price < Pain)"
        else: pressure = "BULLISH COMPRESSION (Price > Pain)"
        
    # 2. MAGNETISM
    magnet = "NONE"
    
    # [FIX] Use Volume POC if available
    if volume_poc > 0:
        magnet = f"${volume_poc:.2f}"
    # Fallback to Top GEX if POC missing (Rare)
    elif not top_gex.empty:
        biggest_strike = top_gex.abs().idxmax()
        magnet = f"${biggest_strike:.2f} (Gamma)"
        
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
def push_to_supabase(id_val, data_dict):
    """Pushes data to Supabase using the REST API."""
    import os
    import requests
    from dotenv import load_dotenv
    
    try:
        load_dotenv('/root/.env')
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        
        if not url or not key:
            print(f"⚠️ [SUPABASE] Missing credentials for {id_val}")
            return
            
        endpoint = f"{url}/rest/v1/nexus_profile"
        headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        
        payload = {
            "id": id_val,
            "data": data_dict
        }
        
        response = requests.post(endpoint, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        print(f"✅ [SUPABASE] Pushed {id_val}")
        
    except Exception as e:
        print(f"❌ [SUPABASE] Push Failed for {id_val}: {e}")

def antigravity_dump(filename, data_dictionary):
    """Atomically dumps data to a JSON file."""
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, "w") as f: json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
        print(f"✅ [HISTORY] Wrote {filename}")
        
        if 'quant' in filename.lower():
            push_to_supabase('nexus_quant', data_dictionary)
        elif 'history' in filename.lower():
            push_to_supabase('nexus_history', data_dictionary)
            
    except Exception as e:
        print(f"❌ HISTORY DUMP ERROR: {e}")

def run_headless_analysis():
    print("🧠 Starting Long-Term Memory Analysis Service (Loop 60m)...")
    import time
    while True:
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧠 Running Analysis Cycle...")
            # HEARTBEAT
            try:
                with open("history_pulse", "w") as f: f.write(str(time.time()))
            except: pass
            
            # 0. HEADLESS FETCH
            print("⬇️ Headless Fetching Data...")
            run_snapshot_cycle(log_func=print)
            
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
                trajectory = calculate_trajectory_logic(spot_price, struct_metrics['flow_pain'], struct_metrics['top_gex'], df, struct_metrics.get('volume_poc', 0))
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
                    "structural_magnets": struct_metrics.get('top_gex_details', []),
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