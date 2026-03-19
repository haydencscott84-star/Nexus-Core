import os
# FILE: spx_profiler_nexus.py
import nexus_lock
nexus_lock.enforce_singleton()
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Static, TabbedContent, TabPane, Input, Button, Footer, Log
from textual.containers import Horizontal, Vertical, Container, VerticalScroll
from textual.reactive import reactive
from rich.text import Text
from rich.table import Table 
from rich.panel import Panel
from rich import box
from textual import events, on, work
import asyncio, aiohttp, datetime, os, re, math, ssl, json, csv
from datetime import timedelta
import numpy as np 
import pandas as pd
import zmq, zmq.asyncio
from pathlib import Path
import time 
import signal
import sys
from collections import deque 
from supabase_bridge import upload_json_to_supabase

try: import pytz; ET = pytz.timezone('US/Eastern')
except: ET = datetime.timezone(datetime.timedelta(hours=-5))

# --- CONFIG ---
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

TARGET_TICKERS = ["SPX", "SPXW"] 
NEXUS_TICKER = "$SPX.X" 
SPY_TICKER = "SPY"
LOG_FILE = "golden_setups_log.csv"
MARKET_LEVELS_FILE = "market_levels.json"
PROFILER_FLOW_PORT = 5571 

# --- TIMING CONFIG ---
FLOW_POLL_SECONDS = 300      
GEX_POLL_SECONDS = 300 # Changed from 60 to 300 to fix API Rate Limit (840/hr -> 168/hr)

# --- SNAPSHOT SCHEDULE (ET) ---
SNAPSHOT_HOURS = [10, 14, 18] 

# --- GLOBAL STATE ---
LIVE_PRICE = {'SPX': 0.0, 'SPY': 0.0}
CURRENT_BASIS = 0.0
ZMQ_FLOW_STATUS = "DISCONNECTED" 
APP_INSTANCE = None

# --- ACCUMULATION STATE ---
SEEN_TRADES = set()
CUMULATIVE_SENTIMENT = 0
SEEN_TRADES = set()
CUMULATIVE_SENTIMENT = 0
LAST_RESET_DATE = None
STATE_FILE = "spx_sentiment_state.json"

def get_now_et():
    return datetime.datetime.now(ET)

def get_trading_date():
    return get_now_et().date()

def load_persistence():
    global SEEN_TRADES, CUMULATIVE_SENTIMENT, LAST_RESET_DATE
    today = get_trading_date()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                saved_state = json.load(f)
                if saved_state.get('date') == today.isoformat():
                    LAST_RESET_DATE = today
                    CUMULATIVE_SENTIMENT = saved_state.get('sentiment', 0)
                    SEEN_TRADES = set(saved_state.get('seen_trades', []))
                else:
                    print(f"[SENTIMENT] State Stale ({saved_state.get('date')}). Resetting for {today.isoformat()}")
                    LAST_RESET_DATE = today
                    CUMULATIVE_SENTIMENT = 0
                    SEEN_TRADES = set()
        except Exception as e:
            print(f"[SENTIMENT] Load Error: {e}")
            LAST_RESET_DATE = today
    else:
        LAST_RESET_DATE = today

# --- ACCUMULATED PREMIUM TRACKER ---
def track_accumulated_premium(orats_chain, state_file="spx_premium_state.json"):
    """Tracks incremental changes in Call/Put volume between scans."""
    today = get_trading_date().isoformat()
    state = {'date': today, 'cum_net_prem': 0.0, 'cum_net_delta': 0.0, 'volumes': {}}
    
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                saved = json.load(f)
                if saved.get('date') == today:
                    state = saved
                else: log_debug(f"Resetting Premium State for {today}")
        except: pass
        
    prev_vols = state.get('volumes', {})
    new_vols = prev_vols.copy()
    
    tick_net_prem = 0
    tick_net_delta = 0
    
    for item in orats_chain:
        try:
            stk = str(item.get('strike', 0)) + "_" + str(item.get('expirDate', ''))
            
            c_vol = float(item.get('callVolume', 0))
            p_vol = float(item.get('putVolume', 0))
            
            # [FIXED] Use new_vols instead of prev_vols to prevent intra-tick duplicates from resetting state
            prev_c = float(new_vols.get(stk, {}).get('c', 0))
            prev_p = float(new_vols.get(stk, {}).get('p', 0))
            
            # Prevent bad data drops from resetting daily accumulation
            if c_vol < prev_c: c_vol = prev_c
            if p_vol < prev_p: p_vol = prev_p
            
            c_diff = c_vol - prev_c
            p_diff = p_vol - prev_p
            
            new_vols[stk] = {'c': c_vol, 'p': p_vol}
            
            if c_diff > 0 or p_diff > 0:
                c_mid = (float(item.get('callBidPrice', 0)) + float(item.get('callAskPrice', 0))) / 2
                if c_mid == 0: c_mid = (float(item.get('callBid', 0)) + float(item.get('callAsk', 0))) / 2
                
                p_mid = (float(item.get('putBidPrice', 0)) + float(item.get('putAskPrice', 0))) / 2
                if p_mid == 0: p_mid = (float(item.get('putBid', 0)) + float(item.get('putAsk', 0))) / 2
                
                c_del = abs(float(item.get('callDelta', 0.5)))
                if 'callDelta' not in item: c_del = abs(float(item.get('delta', 0.5)))
                p_del = -abs(float(item.get('putDelta', -0.5)))
                
                spot_approx = float(item.get('stockPrice') or LIVE_PRICE.get('SPX') or spot_price or 0)
                
                if c_diff > 0 and c_mid > 0:
                    tick_net_prem += (c_diff * c_mid * 100)
                    tick_net_delta += (c_diff * c_del * 100) # Raw Delta Shares
                if p_diff > 0 and p_mid > 0:
                    tick_net_prem -= (p_diff * p_mid * 100)
                    tick_net_delta += (p_diff * p_del * 100) # Raw Delta Shares
                    
        except: pass
        
    state['cum_net_prem'] += tick_net_prem
    state['cum_net_delta'] += tick_net_delta
    state['volumes'] = new_vols
    
    try:
        with open(state_file, 'w') as f: json.dump(state, f)
    except: pass
    
    return state['cum_net_prem'], state['cum_net_delta']

def shutdown_handler(sig, frame):
    print(f"\n[!] Caught signal {sig}. Shutting down...")
    if APP_INSTANCE:
        try:
            APP_INSTANCE.flow_pub_sock.close()
            APP_INSTANCE.zmq_ctx.term()
            print("[+] ZMQ Context Terminated.")
        except: pass
        try:
            loop = asyncio.get_event_loop()
            for task in asyncio.all_tasks(loop): task.cancel()
        except: pass
    sys.exit(0) 
# --- TRAJECTORY LOGIC (Ported from Analyzer) ---
def calculate_trajectory(spot_price, flow_pain, top_gex):
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
        
    # 3. CHARM (Drift) -> Simplified for Live (No DTE access here easily)
    drift = "NEUTRAL"
    
    return f"TRAJECTORY: {pressure} | Magnet: {magnet} | Drift: {drift}"

# --- FILTER SETTINGS ---
MIN_DTE=0; MAX_DTE=45
MIN_PREM=10000      
TOP_N=100           
SHORT_DTE_CUTOFF=3
THEO_TOL = 0.02
URGENCY_THRESHOLD = 0.15 
NEUTRAL_THRESHOLD = 0.05 

def log_debug(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    try:
        with open("spx_profiler_debug.log", "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except: pass

def antigravity_dump(filename, data_dictionary):
    """
    Atomically dumps data and prints a heartbeat log.
    """
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
        
        # NEW: Print a timestamp so the user sees it is alive
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"✅ [HEARTBEAT] Wrote {filename} at {current_time}")
        
    except Exception as e:
        print(f"❌ DUMP ERROR: {e}")

def get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    return ctx

def get_now_et(): 
    try: return datetime.datetime.now(ET)
    except: return datetime.datetime.utcnow() - timedelta(hours=5)

def get_trading_date(ref_date=None):
    if ref_date is None: 
        now = get_now_et()
        # [FIX] Shift Trading Day: If before 06:00 AM, consider it 'yesterday'
        # This keeps yesterday's sentiment/flow visible during overnight/pre-market
        if now.hour < 6:
            ref_date = now.date() - timedelta(days=1)
        else:
            ref_date = now.date()
            
    while ref_date.weekday() >= 5: ref_date -= timedelta(days=1)
    return ref_date



def get_next_n_trading_dates(start_date, n):
    dates = []; current_date = start_date
    holidays = [datetime.date(2025, 11, 27), datetime.date(2025, 12, 25), datetime.date(2026, 1, 1)]
    while len(dates) < n:
        if current_date.weekday() >= 5 or current_date in holidays:
            current_date += timedelta(days=1)
            continue
        dates.append(current_date)
        current_date += timedelta(days=1)
    return dates

def norm_cdf(x): return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0
def fmt_num(val): return f"${val/1e9:.2f}B" if abs(val)>=1e9 else (f"${val/1e6:.1f}M" if abs(val)>=1e6 else f"${val/1e3:.0f}K")
def fmt_gex(val): 
    if val is None: return "-"
    val_abs = abs(val)
    s = f"${val_abs/1e9:.1f}B" if val_abs >= 1e9 else (f"${val_abs/1e6:.0f}M" if val_abs >= 1e6 else f"${val_abs/1e3:.0f}K")
    return "-" + s if val < 0 else s

class StatsEngine:
    def __init__(self, window_size=1000):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.mean = 0.0
        self.std = 0.0

    def process(self, value):
        self.history.append(value)
        if len(self.history) < 2: return 0.0
        vals = np.array(self.history)
        self.mean = np.mean(vals); self.std = np.std(vals)
        return (value - self.mean) / self.std if self.std > 0 else 0.0

# --- GLOBAL STATS ENGINE ---
STATS_ENGINE = StatsEngine()

def analyze_gamma_exposure(strikes_data, spot_price, target_date_str, iv30=0):
    summary_stats = {
        'total_gamma': 0, 'spot_gamma': 0, 'max_pain_strike': None, 'volume_poc_strike': None,
        'volume_poc_sent': 'N/A', 'short_gamma_wall_above': None, 'short_gamma_wall_below': None,
        'long_gamma_wall_above': None, 'long_gamma_wall_below': None,
        'pc_ratio_volume': None, 'pc_ratio_oi': None, 'gex_flip_point': None
    }
    if not strikes_data: return summary_stats
    try:
        df = pd.DataFrame(strikes_data)
        if 'expirDate' not in df.columns: return summary_stats
        
        df['expirDate_dt'] = pd.to_datetime(df['expirDate']).dt.date
        target_dt = pd.to_datetime(target_date_str).date()
        df_target = df[df['expirDate_dt'] == target_dt].copy()
        
        # [DEBUG] Log row counts
        if df_target.empty:
            log_debug(f"DEBUGGING: No strikes found for {target_date_str}. Total DF: {len(df)}")
            return summary_stats
        
        # [FIX] Shift Data Type Coercion ABOVE the IV Mathematical Bound Filtering
        cols = ['gamma', 'callOpenInterest', 'putOpenInterest', 'callVolume', 'putVolume', 'strike']
        # Map ORATS alternatives if primary missing
        if 'gammaSmooth' in df_target.columns and 'gamma' not in df_target.columns: df_target['gamma'] = df_target['gammaSmooth']
        
        for c in cols: 
            if c not in df_target.columns: df_target[c] = 0
            df_target[c] = pd.to_numeric(df_target[c], errors='coerce').fillna(0)
            
        # [REMOVED] IV Range Filtering - Mathematically incorrect to filter options tails for Macro GEX calculation

        if df_target.empty:
             # log_debug(f"DEBUG: Empty target DF for {target_date_str}") 
             return summary_stats
            
        # [DEBUG] Check Sums
        # log_debug(f"Date: {target_date_str} | Calls: {df_target['callOpenInterest'].sum()} | GammaSum: {df_target['gamma'].sum()} | CallVol: {df_target['callVolume'].sum()}")
        
        call_gex = df_target['callOpenInterest'] * 100 * df_target['gamma']
        put_gex = (df_target['putOpenInterest'] * 100 * df_target['gamma'])
        total_gex_units = (call_gex - put_gex) 
        
        summary_stats['total_gamma'] = total_gex_units.sum() * (spot_price**2) * 0.01
        df_target['total_gamma_exp'] = total_gex_units * (spot_price**2) * 0.01
        
        df_target['total_vol'] = df_target['callVolume'] + df_target['putVolume']
        if df_target['total_vol'].sum() > 0:
            poc = df_target.loc[df_target['total_vol'].idxmax()]
            summary_stats['volume_poc_strike'] = float(poc['strike'])
            summary_stats['volume_poc_sent'] = 'C' if poc['callVolume'] > poc['putVolume'] else 'P'

        # [NEW] Spot GEX (Gamma at ATM Strike +/- 1%)
        try:
            near_atm = df_target[(df_target['strike'] >= spot_price * 0.99) & (df_target['strike'] <= spot_price * 1.01)]
            summary_stats['spot_gamma'] = float(near_atm['total_gamma_exp'].sum())
        except: pass

        # [NEW] P/C Ratios
        total_call_vol = df_target['callVolume'].sum()
        total_put_vol = df_target['putVolume'].sum()
        if total_call_vol > 0:
            summary_stats['pc_ratio_volume'] = total_put_vol / total_call_vol
        
        total_call_oi = df_target['callOpenInterest'].sum()
        total_put_oi = df_target['putOpenInterest'].sum()
        if total_call_oi > 0:
            summary_stats['pc_ratio_oi'] = total_put_oi / total_call_oi

        # Walls & Flip Point
        
        sig_gex = df_target[df_target['total_gamma_exp'].abs() > 1.0].copy()
        
        if not sig_gex.empty:
            short_gex = sig_gex[sig_gex['total_gamma_exp'] < 0]
            if not short_gex.empty:
                above = short_gex[short_gex['strike'] > spot_price]; below = short_gex[short_gex['strike'] < spot_price]
                if not above.empty: 
                    row = above.loc[above['total_gamma_exp'].idxmin()]
                    summary_stats['short_gamma_wall_above'] = float(row['strike'])
                if not below.empty: 
                    row = below.loc[below['total_gamma_exp'].idxmin()]
                    summary_stats['short_gamma_wall_below'] = float(row['strike'])
            
            long_gex = sig_gex[sig_gex['total_gamma_exp'] > 0]
            if not long_gex.empty:
                above = long_gex[long_gex['strike'] > spot_price]; below = long_gex[long_gex['strike'] < spot_price]
                if not above.empty: 
                    row = above.loc[above['total_gamma_exp'].idxmax()]
                    summary_stats['long_gamma_wall_above'] = float(row['strike'])
                if not below.empty: 
                    row = below.loc[below['total_gamma_exp'].idxmax()]
                    summary_stats['long_gamma_wall_below'] = float(row['strike'])

        # Fallback for Short Wall Above if missing (Blue Sky)
        if summary_stats['short_gamma_wall_above'] is None and not sig_gex.empty:
             pos_above = sig_gex[(sig_gex['strike'] > spot_price) & (sig_gex['total_gamma_exp'] > 0)]
             if not pos_above.empty:
                 row = pos_above.loc[pos_above['total_gamma_exp'].idxmax()]
                 summary_stats['short_gamma_wall_above'] = float(row['strike']) # Use Call Wall as proxy

        # Flip Point
        df_sorted = df_target.sort_values('strike')
        strikes = df_sorted['strike'].values
        gammas = df_sorted['total_gamma_exp'].values
        for i in range(len(strikes) - 1):
            g1 = gammas[i]; g2 = gammas[i+1]
            if (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
                if abs(g1) < abs(g2): flip = strikes[i]
                else: flip = strikes[i+1]
                if abs(flip - spot_price) < (spot_price * 0.05):
                    summary_stats['gex_flip_point'] = float(flip)
                    break
        
        # Max Pain
        strikes_u = df_target['strike'].unique()
        if len(strikes_u) > 0:
            total_values = []
            sample = [s for s in strikes_u if s % 5 == 0]
            for px in sample:
                val = ((px - df_target['strike']).clip(lower=0) * df_target['callOpenInterest']).sum() + ((df_target['strike'] - px).clip(lower=0) * df_target['putOpenInterest']).sum()
                total_values.append((px, val))
            if total_values: summary_stats['max_pain_strike'] = float(min(total_values, key=lambda x: x[1])[0])

        # [DEBUG] Log Summary Stats
        try:
             log_debug(f"Summary for {target_date_str}: Pain={summary_stats.get('max_pain_strike')} POC={summary_stats.get('volume_poc_strike')} Flip={summary_stats.get('gex_flip_point')}")
        except: pass
        
        return summary_stats
    except Exception as e:
        print(f"[ERROR] GEX Calc Failed: {e}")
        import traceback; traceback.print_exc()
        return summary_stats

def score_profiler_data(contracts: list[dict]) -> int:
    sentiment_score = 0
    if not contracts: return 0
    for contract in contracts:
        try:
            # Basic net conviction scoring (BULL=+1, BEAR=-1)
            if "BULL" in contract.get('conf', ''): sentiment_score += 1
            elif "BEAR" in contract.get('conf', ''): sentiment_score -= 1
        except: pass
    return sentiment_score

# --- SNAPSHOT LOAD ---
def load_gex_snapshot():
    try:
        if os.path.exists("nexus_gex_static.json"):
            with open("nexus_gex_static.json", 'r') as f:
                return json.load(f)
    except: pass
    return {}

async def stream_nexus():
    global CURRENT_BASIS
    ctx = zmq.asyncio.Context(); sock = ctx.socket(zmq.SUB)
    try:
        sock.connect("tcp://localhost:5555")
        sock.setsockopt_string(zmq.SUBSCRIBE, NEXUS_TICKER); sock.setsockopt_string(zmq.SUBSCRIBE, SPY_TICKER)
        while True:
            msg = await sock.recv_multipart(); topic = msg[0].decode(); d = json.loads(msg[1])
            if "Last" in d:
                val = float(d['Last'])
                if topic == NEXUS_TICKER: LIVE_PRICE['SPX'] = val
                elif topic == SPY_TICKER: LIVE_PRICE['SPY'] = val
                if LIVE_PRICE['SPX'] > 0 and LIVE_PRICE['SPY'] > 0: CURRENT_BASIS = LIVE_PRICE['SPX'] - (LIVE_PRICE['SPY'] * 10)
    except: pass

async def fetch_orats_live(s, ticker):
    """Fetch ORATS strikes with fallback to delayed data."""
    log_debug(f"DEBUG: Fetching ORATS Live Strikes for {ticker}...")
    
    # Try Live First
    try:
        async with s.get("https://api.orats.io/datav2/live/strikes", params={'token': ORATS_API_KEY, 'ticker': ticker}, timeout=45) as r:
            if r.status == 200: 
                data = await r.json()
                rows = data.get('data', [])
                log_debug(f"DEBUG: ORATS LIVE Success. {len(rows)} rows.")
                return rows
            elif r.status == 403:
                log_debug(f"DEBUG: ORATS 403 (Live Denied). Falling back to delayed...")
            else:
                txt = await r.text()
                log_debug(f"DEBUG: ORATS Live Error {r.status}: {txt[:100]}")
    except Exception as e: log_debug(f"DEBUG: ORATS Live Exception: {e}")

    # Fallback to Delayed
    try:
        log_debug(f"DEBUG: Attempting ORATS Delayed Endpoint...")
        async with s.get("https://api.orats.io/datav2/strikes", params={'token': ORATS_API_KEY, 'ticker': ticker}, timeout=45) as r:
            if r.status == 200: 
                data = await r.json()
                rows = data.get('data', [])
                log_debug(f"DEBUG: ORATS DELAYED Success. {len(rows)} rows.")
                return rows
            else:
                txt = await r.text()
                log_debug(f"DEBUG: ORATS Delayed Error {r.status}: {txt[:100]}")
    except Exception as e: log_debug(f"DEBUG: ORATS Delayed Exception: {e}")
    
    return []

async def fetch_ticker_data(session, ticker, fetch_gex=True):
    if ticker == "SPXW" or not fetch_gex:
        t_orats_live = asyncio.sleep(0, result=[])
    else:
        t_orats_live = fetch_orats_live(session, ticker)

    if ticker == "SPXW":
        t_orats_sum = asyncio.sleep(0, result=None); t_uw_iv = asyncio.sleep(0, result=None)
    else:
        t_orats_sum = session.get("https://api.orats.io/datav2/live/summaries", params={'token': ORATS_API_KEY, 'ticker': ticker}, timeout=10)
        t_uw_iv = asyncio.sleep(0, result=None)
    
    t_uw_flow = asyncio.sleep(0, result=None)
    
    return await asyncio.gather(t_orats_sum, t_uw_iv, t_uw_flow, t_orats_live, return_exceptions=True)

async def fetch_combined_data(session, fetch_gex=True):
    tasks = [fetch_ticker_data(session, t, fetch_gex=fetch_gex) for t in TARGET_TICKERS]
    results = await asyncio.gather(*tasks)
    
    try:
        async with session.get("https://api.orats.io/datav2/live/summaries", params={'token': ORATS_API_KEY, 'ticker': "SPY"}, timeout=5) as r:
             if r.status == 200: d = (await r.json()).get('data', [{}])[0]; LIVE_PRICE['SPY'] = float(d.get('stockPrice') or 0)
    except: pass
    
    master_uw = []; master_orats = []
    final_ctx = {'price':0.0,'iv30':0.0,'iv_rank':0.0,'prev':0.0}
    
    for i, res_set in enumerate(results):
        r_sum, r_iv, r_flow, r_live = res_set
        if i == 0: 
            if not isinstance(r_sum, Exception) and r_sum and hasattr(r_sum, 'status') and r_sum.status==200:
                d=(await r_sum.json()).get('data',[{}])[0]
                final_ctx['price']=float(d.get('stockPrice')or 0); final_ctx['iv30']=float(d.get('iv30d')or 0); final_ctx['prev']=float(d.get('prevClose')or 0)
                if LIVE_PRICE['SPX'] == 0: LIVE_PRICE['SPX'] = final_ctx['price']
            
            # [FIX] Robust Fallback if ORATS returns 0 for SPX (Common Issue)
            if final_ctx['price'] == 0 and LIVE_PRICE.get('SPY', 0) > 0:
                est_spx = LIVE_PRICE['SPY'] * 10 + 30 # Approx Basis (+30)
                log_debug(f"WARNING: ORATS SPX Price 0. Using SPY Proxy: {est_spx}")
                final_ctx['price'] = est_spx
                LIVE_PRICE['SPX'] = est_spx
                
            if not isinstance(r_iv, Exception) and r_iv and hasattr(r_iv, 'status') and r_iv.status==200: d=(await r_iv.json()).get('data',[]); final_ctx['iv_rank']=float(d[-1].get('iv_rank_1y')or 0) if d else 0
        
        if not isinstance(r_flow, Exception) and hasattr(r_flow, 'status') and r_flow.status==200: master_uw.extend((await r_flow.json()).get('data',[]))
        
        if fetch_gex and not isinstance(r_live, Exception) and isinstance(r_live, list): master_orats.extend(r_live)
    
    global CURRENT_BASIS
    if CURRENT_BASIS == 0 and LIVE_PRICE['SPX'] > 0 and LIVE_PRICE['SPY'] > 0: CURRENT_BASIS = LIVE_PRICE['SPX'] - (LIVE_PRICE['SPY'] * 10)
    
    # --- GEX CALCULATION ---
    gex_summaries = []
    # [FIX] Increased from 6 to 14 (User Request)
    dates = get_next_n_trading_dates(get_trading_date(), 10)
    
    # [NEW] Aggregators for Trajectory Calculation
    agg_flow_pain = 0
    agg_top_gex = pd.Series(dtype=float)
    
    if fetch_gex and master_orats and final_ctx['price'] > 0:
        log_debug(f"DEBUG: Analyzing GEX for {len(master_orats)} options. Spot: {final_ctx['price']}")
        import functools
        loop = asyncio.get_running_loop()
        
        def calc_agg_magnet(master_orats, price):
            try:
                orats_df = pd.DataFrame(master_orats)
                if orats_df.empty: return pd.Series(dtype=float)
                cols = ['gamma', 'callOpenInterest', 'putOpenInterest', 'strike']
                for c in cols: orats_df[c] = pd.to_numeric(orats_df[c], errors='coerce').fillna(0)
                orats_df['total_gamma_exp'] = (orats_df['callOpenInterest'] - orats_df['putOpenInterest']) * orats_df['gamma'] * 100 * (price**2) * 0.01
                return orats_df.groupby('strike')['total_gamma_exp'].sum().abs().nlargest(1)
            except:
                return pd.Series(dtype=float)

        for d in dates: 
            d_str = d.strftime('%Y-%m-%d')
            # [OPTIMIZED] Offload CPU-intensive GEX calc to thread pool to prevent UI freeze
            # [NEW] Pass IV30d for Range Filtering
            stats = await loop.run_in_executor(None, functools.partial(analyze_gamma_exposure, master_orats, final_ctx["price"], d_str, iv30=final_ctx['iv30']))
            gex_summaries.append(stats)
            
            # Use the first valid expiry (0DTE/1DTE) for Flow Pain Proxy
            mp = stats.get('max_pain_strike')
            if agg_flow_pain == 0 and mp is not None and mp > 0:
                agg_flow_pain = mp
        
        # [DEBUG] Log result count
        log_debug(f"DEBUGGING: Generated {len(gex_summaries)} GEX summaries.")

        if master_orats:
            agg_top_gex = await loop.run_in_executor(None, calc_agg_magnet, master_orats, final_ctx['price'])

    # --- CALCULATE & INJECT TRAJECTORY ---
    trj = calculate_trajectory(final_ctx['price'], agg_flow_pain, agg_top_gex)
    final_ctx['trajectory'] = trj
            
    return final_ctx, master_uw, master_orats, gex_summaries, dates

def process(uw, orats, ctx):
    global SEEN_TRADES, CUMULATIVE_SENTIMENT, LAST_RESET_DATE
    spot=ctx['price']; iv=ctx['iv30']; today=get_now_et().date(); res=[]; net=0; omap={}; bull_tot=0.0; bear_tot=0.0
    
    if orats:
        for r in orats:
            try:
                exp = r['expirDate']; stk = float(r['strike'])
                if 'smv' in r and 'optionType' in r: omap[f"{exp}|{stk:.1f}|{r['optionType'][0].upper()}"] = float(r['smv'])
                else:
                     if 'callValue' in r: omap[f"{exp}|{stk:.1f}|C"] = float(r['callValue']); 
                     if 'putValue' in r:  omap[f"{exp}|{stk:.1f}|P"] = float(r['putValue'])
            except: pass
            
    alerts = [] 
    for i, t in enumerate(uw):
        try:
            sym=t.get('option_symbol'); m=re.search(r'(\d{2})(\d{2})(\d{2})([CP])(\d{8})$', sym)
            if not m: continue
            yy,mm,dd,tc,sr=m.groups(); exp=datetime.date(2000+int(yy),int(mm),int(dd)); dte=max(0,(exp-today).days)
            stk=float(sr)/1000; otype='C' if tc=='C' else 'P'; prem=float(t.get('premium')or 0)
            mkt=float(t.get('close') or (float(t.get('bid')or 0)+float(t.get('ask')or 0))/2)
            vol=int(t.get('volume')or 1); oi=int(t.get('open_interest')or 0)
            if (vol/oi if oi>0 else 100) < 0.7 and prem < 500000: continue
            
            # [DEBUG] EDGE LOOKUP with Robust Keys
            k1 = f"{exp.isoformat()}|{stk:.1f}|{tc}"
            k2 = f"{exp.isoformat()}|{int(stk)}|{tc}" # Try integer strike
            k3 = f"{exp.isoformat()}|{stk}|{tc}"      # Try raw float
            
            theo = omap.get(k1) or omap.get(k2) or omap.get(k3) or 0.0
            
            if theo == 0.0 and i < 1: 
                 matches = [k for k in omap.keys() if str(int(stk)) in k]
                 with open("spx_debug.log", "a") as f:
                     f.write(f"[DEBUG] Edge Fail: KeyGen=[{k1}] OMAP_Sample={list(omap.keys())[:3]}\n")

            edge=0.0; val_sc=0
            if theo > 0:
                edge = ((theo - mkt) / theo) * 100
                if edge > 2.0: val_sc = 1
                elif edge < -2.0: val_sc = -1
            
            av=int(t.get('ask_side_volume')or 0); bv=int(t.get('bid_side_volume')or 0); urg=(av-bv)/vol
            side_tag = "(MID)"; prem_signed = 0
            if urg > NEUTRAL_THRESHOLD: side_tag = "(BOT)"; prem_signed = prem
            elif urg < -NEUTRAL_THRESHOLD: side_tag = "(SOLD)"; prem_signed = -prem
            
            # --- Z-SCORE CALCULATION ---
            z_score = STATS_ENGINE.process(prem)
            is_whale = abs(z_score) > 3.0
            
            conf_score = 0; abs_urg = abs(urg)
            if abs_urg > URGENCY_THRESHOLD: conf_score += 1
            if abs_urg > 0.5: conf_score += 1
            if val_sc == 1: conf_score += 1
            if oi > 0 and (vol/oi) > 2.0: conf_score += 1 
            if is_whale: conf_score += 2 # Boost confidence for whales 
            trade_sentiment = "NEUTRAL"
            if otype == 'C':
                if urg > NEUTRAL_THRESHOLD: trade_sentiment = "BULL"
                elif urg < -NEUTRAL_THRESHOLD: trade_sentiment = "BEAR"
            elif otype == 'P':
                if urg > NEUTRAL_THRESHOLD: trade_sentiment = "BEAR"
                elif urg < -NEUTRAL_THRESHOLD: trade_sentiment = "BULL"
            if trade_sentiment == "BEAR": conf_score = -abs(conf_score)
            elif trade_sentiment == "NEUTRAL": conf_score = 0
            if conf_score >= 3: conf = "STRONG BULL"
            elif conf_score >= 1: conf = "BULL"
            elif conf_score <= -3: conf = "STRONG BEAR"
            elif conf_score <= -1: conf = "BEAR"
            else: conf = "NEUTRAL"
            
            if "BULL" in conf: bull_tot += prem; net += prem
            elif "BEAR" in conf: bear_tot += prem; net -= prem
            else:
                if edge > 0.5 or urg > 0.05: net += prem
                elif edge < -0.5 or urg < -0.05: net -= prem
            
            # --- V/OI FILTER ---
            # User Request: Only see V/OI >= 1.0 (Strict "Unusual" Activity)
            voi = vol/oi if oi > 0 else 100
            if voi < 1.0: continue

            if conf == "NEUTRAL": continue
            if side_tag == "(MID)": continue
            
            # --- IV RANGE FILTER (30-Day Implied Move) ---
            # Range = Spot * IV30 * sqrt(30/365)
            # User Feedback: "I can see two trades below the threshold"
            # REPAIR: Sync filter EXACTLY to the header display (1.0x Standard Deviation).
            if spot > 0 and iv > 0:
                im = spot * iv * math.sqrt(30.0 / 365.0)
                upper = spot + im
                lower = spot - im
                if stk < lower or stk > upper: continue

            # --- OTM FILTER (Moneyness) ---
            # Only allow Out-The-Money trades (calls > spot, puts < spot)
            if spot > 0:
                # If Call, Strike must be GREATER than Spot (OTM)
                # If ITM (Strike < Spot), skip.
                if otype == 'C' and stk < spot: continue
                # If Put, Strike must be LESS than Spot (OTM)
                # If ITM (Strike > Spot), skip.
                if otype == 'P' and stk > spot: continue
            
            # --- ACCUMULATION LOGIC (WITH ROBUST PERSISTENCE) ---
            global SEEN_TRADES, CUMULATIVE_SENTIMENT, LAST_RESET_DATE
            today = get_trading_date()
            
            # Initial Load (Fallback)
            if LAST_RESET_DATE is None:
                load_persistence()

            # Daily Reset Check
            if LAST_RESET_DATE != today:
                print(f"[SENTIMENT] NEW DAY DETECTED. Resetting Score (Old: {CUMULATIVE_SENTIMENT})")
                SEEN_TRADES.clear()
                CUMULATIVE_SENTIMENT = 0
                LAST_RESET_DATE = today
                # Wipe file
                try: 
                    with open(STATE_FILE, 'w') as f: json.dump({'date': today.isoformat(), 'sentiment': 0, 'seen_trades': []}, f)
                except: pass
            
            # Trade Signature
            tr_id = t.get('id')
            if not tr_id:
                tr_sig = f"{sym}_{t.get('timestamp')}_{prem}_{vol}"
                tr_id = hash(tr_sig)
                
            if tr_id not in SEEN_TRADES:
                # [FIX] ROBUST TIMEZONE-AWARE DATE CHECK (UTC -> ET)
                try:
                    ts_str = t.get('timestamp', '')
                    if ts_str.endswith('Z'):
                        dt_utc = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    else:
                        dt_utc = datetime.datetime.fromisoformat(ts_str)
                    
                    # Convert to ET
                    dt_et = dt_utc.astimezone(ET)

                    # [DEBUG] Date Check
                    # print(f"[DEBUG] Processing {tr_id}: TradeDate={dt_et.date()} Today={today} Conf={conf}")

                    if dt_et.date().isoformat() == today.isoformat():
                        # [NEW] WEIGHTED SCORING SYSTEM
                        score_contrib = 0.0
                        
                        # 1. Premium Weight
                        prem_weight = 0.1 # Noise (<10k)
                        if prem >= 500000: prem_weight = 5.0    # Whale
                        elif prem >= 200000: prem_weight = 2.0  # Large
                        elif prem >= 50000: prem_weight = 1.0   # Standard
                        elif prem >= 10000: prem_weight = 0.5   # Small
                        
                        # 2. Conviction/Direction
                        direction = 0
                        conf_mult = 1.0
                        
                        if "BULL" in conf: 
                            direction = 1
                            if "STRONG" in conf: conf_mult = 1.5
                        elif "BEAR" in conf: 
                            direction = -1
                            if "STRONG" in conf: conf_mult = 1.5
                        else:
                            # [FIX] Capture "Lean" Trades (Previously ignored)
                            if urg > 0.05 or edge > 1.0: 
                                direction = 1; conf_mult = 0.5 # Lean Bull
                            elif urg < -0.05 or edge < -1.0: 
                                direction = -1; conf_mult = 0.5 # Lean Bear
                        
                        # 3. Final Calculation
                        if direction != 0:
                            score_contrib = direction * prem_weight * conf_mult
                            
                            old_score = CUMULATIVE_SENTIMENT
                            CUMULATIVE_SENTIMENT += score_contrib
                            SEEN_TRADES.add(tr_id)
                            
                            # Log significant changes
                            with open("debug_sentiment.log", "a") as f:
                                f.write(f"[{datetime.datetime.now()}] ID:{tr_id} Prem:${prem:,.0f} Urg:{urg:.2f} -> Score:{score_contrib:+.1f} Total:{CUMULATIVE_SENTIMENT:.1f}\n")
                            print(f"[SENTIMENT] Trade {tr_id} -> {score_contrib:+.1f} (Total: {CUMULATIVE_SENTIMENT:.1f})")
                        else:
                            # Truly Neutral (Low Urg, Low Edge) - Skip
                            pass
                    else:
                        pass # Skipping non-today trades (History)
                        
                except Exception as e: print(f"[SENTIMENT] Process Error: {e}")


            win=50; be=stk+mkt if otype=='C' else stk-mkt
            if spot>0 and iv>0 and dte>0: win=(1.0-norm_cdf(math.log(be/spot)/(iv*math.sqrt(dte/365.0))))*100 if otype=='C' else norm_cdf(math.log(be/spot)/(iv*math.sqrt(dte/365.0)))*100
            elif dte==0: win=100 if (otype=='C' and spot>stk) or (otype=='P' and spot<stk) else 0
            
            # [PATCHED] Added 'delta' and 'gamma' capture
            greeks_dict = t.get('greeks') or {}
            
            def safe_greek(key):
                val = t.get(key) or greeks_dict.get(key) or 0.0
                try: return float(val)
                except: return 0.0

            delta = safe_greek('delta')
            gamma = safe_greek('gamma')
            vega = safe_greek('vega')
            theta = safe_greek('theta')
            
            res.append({
                'sym':sym,'exp':exp.isoformat(),'dte':dte,'stk':stk,'type':otype,
                'prem':prem,'vol':vol,'oi':oi,'mkt':mkt,'theo':theo,'edge':edge,
                'conf':conf,'be':be,'win':win, 'is_golden': False, 'side_tag': side_tag, 
                'z_score': z_score, 'is_whale': is_whale, 'delta': delta, 'gamma': gamma,
                'vega': vega, 'theta': theta,
                'underlying_price': spot
            })
        except: continue
    
    # [PERSISTENCE] Safe Save State
    if LAST_RESET_DATE == get_trading_date():
        try:
            state_data = {
                'date': LAST_RESET_DATE.isoformat(),
                'sentiment': CUMULATIVE_SENTIMENT,
                'seen_trades': list(SEEN_TRADES)
            }
            temp_file = f"{STATE_FILE}.tmp"
            with open(temp_file, 'w') as f: json.dump(state_data, f)
            os.replace(temp_file, STATE_FILE)
        except Exception as e: print(f"[SENTIMENT] Save Failed: {e}")

    return sorted(res, key=lambda x:x['prem'], reverse=True), alerts[:4]

def format_flow_row(r):
    style_base = "bold " if r['is_golden'] else "dim "
    edge_txt = Text(f"{r['edge']:+.1f}%", style="bold green" if r['edge']>1.5 else ("bold red" if r['edge']<-1.5 else "dim white"))
    conf_clean = r['conf'].replace('STRONG ','').replace('CAUTION ','')
    if r['is_golden']: conf_clean = "★ " + conf_clean
    conf_style = "bold green" if "BULL" in r['conf'] else ("bold red" if "BEAR" in r['conf'] else "dim white")
    if CURRENT_BASIS != 0: spy_equiv = (r['stk'] - CURRENT_BASIS) / 10; stk_str = f"${r['stk']:.0f} ({spy_equiv:.1f}) {r['type']}"
    else: spy_equiv = r['stk'] / 10; stk_str = f"${r['stk']:.0f} ({spy_equiv:.0f}) {r['type']}"
    contract_txt = Text(stk_str + "   ", style=style_base + ("green" if r['type']=='C' else "red"))
    side_color = "green" if r['side_tag'] == "(BOT)" else ("red" if r['side_tag'] == "(SOLD)" else "white")
    side_txt = Text(f" {r['side_tag']} ", style=f"bold {side_color}")
    try: d_obj = datetime.datetime.strptime(r['exp'], '%Y-%m-%d'); date_short = d_obj.strftime('%b %d')
    except: date_short = r['exp']
    edge_padded = Text(f" {r['edge']:+.1f}% ", style="bold green" if r['edge']>1.5 else ("bold red" if r['edge']<-1.5 else "dim white"))
    conf_padded = Text(f" {conf_clean} ", style=conf_style)
    be_padded = f" ${r['be']:.2f} "
    z_style = "bold white on red" if r['is_whale'] else ("bold yellow" if abs(r['z_score']) > 2.0 else "dim white")
    z_txt = Text(f"{r['z_score']:.1f}σ", style=z_style)
    row=(date_short, str(r['dte']), contract_txt, side_txt, fmt_num(r['prem']), Text(f"{r['vol']/r['oi']:.1f}x" if r['oi']>0 else "NEW", style="bold yellow" if (r['oi']>0 and r['vol']/r['oi']>5) else "white"), f"${r['mkt']:.2f}", edge_padded, conf_padded, be_padded, Text(f"{r['win']:.0f}%", style="green" if r['win']>60 else ("red" if r['win']<40 else "white")), z_txt)
    return row

class AlertBox(Static):
    def update_alerts(self, alerts):
        if not alerts: self.update(Text.from_markup("\n[dim]Scanning for setups...[/]", justify="center")); self.styles.height = 3; self.remove_class("active")
        else: self.styles.height = len(alerts) + 2; self.add_class("active"); txt = "\n".join(alerts); self.update(Text.from_markup(f"[bold white on blue] 識 SMART SETUPS (Action Required) [/]\n{txt}"))

class FlowBox(Static):
    def on_mount(self):
        self.update_content({})

    def update_content(self, uw_flow_data):
        strike_data = uw_flow_data.get('strike_data', {})
        delta_ticks = uw_flow_data.get('delta_ticks', [])
        
        net_flow_val = 0
        if delta_ticks:
            for tick in delta_ticks:
                net_flow_val += float(tick.get('net_premium', 0) or 0)
            current_delta = float(delta_ticks[-1].get('net_delta') or 0)
        else:
            current_delta = 0

        cp = strike_data.get('total_call_premium', 0) or 0
        pp = strike_data.get('total_put_premium', 0) or 0
        net_vol_val = cp - pp
        
        if abs(net_flow_val) > 1:
            final_val = net_flow_val
            label_str = "Net Flow (Bull/Bear):"
        else:
            final_val = net_vol_val
            label_str = "Net Prem (Call-Put):"

        z_score = float(uw_flow_data.get('flow_z_score', 0.0))
        z_str = ""
        if z_score > 2.0: z_str = f" [bold green](σ +{z_score:.1f})[/]"
        elif z_score < -2.0: z_str = f" [bold red](σ {z_score:.1f})[/]"
        elif abs(z_score) > 1.0: z_str = f" [white](σ {z_score:.1f})[/]"
        
        top_call_str = "N/A"
        if strike_data.get('top_call_strike'):
            top_call_str = f"${strike_data['top_call_strike']['strike']:g}"
        
        top_put_str = "N/A"
        if strike_data.get('top_put_strike'):
            top_put_str = f"${strike_data['top_put_strike']['strike']:g}"

        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(); t.add_column(justify="right")
        
        def safe_fmt(v, plus=False):
            val_abs = abs(v)
            s = f"${val_abs/1e9:.2f}B" if val_abs>=1e9 else (f"${val_abs/1e6:.1f}M" if val_abs>=1e6 else f"${val_abs/1e3:.0f}K")
            if v > 0 and plus: return "+" + s
            if v < 0: return "-" + s
            return s
            
        t.add_row(label_str, f"[{'green' if final_val>0 else 'red'}]{safe_fmt(final_val, True)}[/]{z_str}")
        t.add_row("Net Delta:", f"[{'green' if current_delta>0 else 'red'}]{safe_fmt(current_delta, True)}[/]")
        t.add_row(Text("Call Support", style="bold green"), f"[bold green]{top_call_str}[/]")
        t.add_row(Text("Put Resist", style="bold #FF0000"), f"[bold #FF0000]{top_put_str}[/]")
        
        self.update(Panel(t, title="[bold white]Premium & Delta Flow (ORATS)[/]", border_style="white"))

class WeeklyGexTable(DataTable):
    can_focus = True
    
    def on_mount(self):
        self.border_title = "Weekly GEX Structure (ORATS)"
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.col_keys = self.add_columns("Date", "DTE", "Total GEX", "Spot GEX", "Max Pain", "Vol POC", "Flip Pt", "Accel (R)", "Pin (S)", "P/C (Vol)", "P/C (OI)")

    def update_content(self, dates, gex_summaries):
        if not gex_summaries or len(dates) != len(gex_summaries):
            if not self.row_count:
                self.add_row("Waiting for GEX data...", "", "", "", "", "", "", "", "", "", "", key="wait")
            return
            
        existing_keys = [r.value for r in self.rows.keys()]
        if "wait" in existing_keys:
            self.clear()
            existing_keys = []

        seen_keys = set()
        for i, summary in enumerate(gex_summaries):
            date_str = dates[i].strftime('%Y-%m-%d'); dte = (dates[i] - get_trading_date()).days
            row_key = date_str
            seen_keys.add(row_key)
            def fmt_s(val):
                try:
                    if val is None: return "N/A"
                    # Handle potential Series/Array ambiguity
                    if hasattr(val, 'empty') and val.empty: return "N/A"
                    val_f = float(val)
                    if val_f == 0: return "N/A"
                except: return "N/A"
                
                if CURRENT_BASIS != 0: spy_val = (val_f - CURRENT_BASIS) / 10; return f"${val_f:.0f} ({spy_val:.1f})"
                return f"${val_f:.0f}"
            gex = summary.get('total_gamma'); gex_str = fmt_gex(gex); gex_style = "green" if (gex or 0) > 0 else "red"
            sgex = summary.get('spot_gamma'); sgex_str = fmt_gex(sgex); sgex_style = "green" if (sgex or 0) > 0 else "red"
            max_pain_str = fmt_s(summary.get('max_pain_strike')); pin_s = fmt_s(summary.get('short_gamma_wall_below'))
            
            # Accel (R) Logic
            accel_r = fmt_s(summary.get('short_gamma_wall_above'))
            accel_type = summary.get('short_gamma_wall_above_type', 'NEG')
            accel_style = "bold cyan" if accel_type == 'POS' else "red"
            
            poc_strike = summary.get('volume_poc_strike'); poc_str = "N/A"
            if poc_strike:
                poc_sent = "C" if summary.get('volume_poc_call_vol', 0) > summary.get('volume_poc_put_vol', 0) else "P"
                poc_val_str = fmt_s(poc_strike); poc_str = f"{poc_val_str} ([{'green' if poc_sent == 'C' else 'red'}]{poc_sent}[/])"
            
            flip_pt = summary.get('gex_flip_point')
            flip_str = fmt_s(flip_pt) if flip_pt else "N/A"
            flip_style = "bold cyan" if flip_pt else "dim"

            row_data = (
                date_str, 
                str(dte),
                Text(gex_str, style=gex_style), 
                Text(sgex_str, style=sgex_style),
                Text(max_pain_str, style="white"), 
                Text.from_markup(poc_str, style="white"),
                Text(flip_str, style=flip_style),
                Text(accel_r, style=accel_style), 
                Text(pin_s, style="white"),
                Text(f"{(summary.get('pc_ratio_volume') or 0):.2f}", style="dim"), 
                Text(f"{(summary.get('pc_ratio_oi') or 0):.2f}", style="dim")
            )

            if row_key in existing_keys:
                for col_idx, cell_value in enumerate(row_data):
                    self.update_cell(row_key, self.col_keys[col_idx], cell_value, update_width=False)
            else:
                self.add_row(*row_data, key=row_key)
                
        # Remove any stale rows
        for key in list(existing_keys):
            if key not in seen_keys:
                self.remove_row(key)

class InfoBox(Container):
    def compose(self) -> ComposeResult:
        yield Static(id="info_lbl")
        with Horizontal(id="btn_row"):
            yield Button("REFRESH", id="btn_refresh", variant="primary")
            yield Button("SNAPSHOT", id="btn_snapshot", variant="warning")
            
    def on_mount(self): self.query_one("#info_lbl", Static).update(Text.from_markup("SPX: [dim]Initializing...[/]"))
    def update(self, content): self.query_one("#info_lbl", Static).update(content)
    def update_data(self, ctx, agg_d0, agg_d1, daily_cum_sent=0, net_flow_premium=0, magnet_level=0): 
        p=LIVE_PRICE['SPX'] or ctx['price']; prev=ctx['prev']; pct=((p-prev)/prev)*100 if prev>0 else 0
        if CURRENT_BASIS != 0: spread_str = f"Spread: {CURRENT_BASIS:+.2f}"; spy_est = (p - CURRENT_BASIS) / 10; spy_str = f"SPY ~${spy_est:.2f}"
        else: spread_str = "Spread: Calc..."; spy_str = "SPY: Calc..."
        
        # [NEW] Daily Tally Display
        sent_style = "bold green" if daily_cum_sent > 0 else ("bold red" if daily_cum_sent < 0 else "white")
        daily_sent_str = f"Daily Sentiment: [{sent_style}]{daily_cum_sent:+.1f}[/]"
        
        # [NEW] Bridge to Streamlit
        try:
            with open("/Users/haydenscott/Desktop/Local Scripts/spx_premium_state.json", "w") as f:
                json.dump({
                    "cum_net_prem": net_flow_premium,
                    "cum_net_delta": current_delta,
                    "timestamp": datetime.datetime.now().isoformat()
                }, f)
        except Exception as e: pass
        
        
        # [NEW] Premium Flow Header Tracker
        p_style = "bold green" if net_flow_premium > 0 else "bold red"
        def fmt_num(val):
            v_abs = abs(val)
            base = f"${v_abs/1e9:.2f}B" if v_abs>=1e9 else (f"${v_abs/1e6:.1f}M" if v_abs>=1e6 else f"${v_abs/1e3:.0f}K")
            if val < 0: return "-$" + base[1:]
            return base
        p_str = fmt_num(net_flow_premium)
        if net_flow_premium > 0: p_str = "+" + p_str
        flow_str = f" | [white]Net Flow:[/] [{p_style}]{p_str}[/]"

        
        status_color = "green" if ZMQ_FLOW_STATUS == "CONNECTED" else ("red" if "FAIL" in ZMQ_FLOW_STATUS else "yellow")
        status_str = f"Flow ZMQ: [{status_color}]● {ZMQ_FLOW_STATUS}[/]"
        
        # [NEW] Range Display
        range_str = ""
        iv = ctx.get('iv30', 0)
        if p > 0 and iv > 0:
            imp = p * iv * math.sqrt(30.0/365.0)
            range_str = f" | [bold cyan]Range: {p-imp:.0f}-{p+imp:.0f} (IV:{iv:.1%})[/]"
            
        mag_str = f" | [magenta]Magnet: ${magnet_level:.0f}[/]" if magnet_level > 0 else " | [dim]Magnet: WAIT[/]"

        txt = (f"SPX: [bold]${p:,.2f}[/] ({spy_str}) [{spread_str}] [{'green' if pct>=0 else 'red'}]{pct:+.2f}%{flow_str}{mag_str} | IVR: {ctx['iv_rank']:.0f}%{range_str}\n{daily_sent_str} | {status_str}")
        self.query_one("#info_lbl", Static).update(Text.from_markup(txt))

class StatusDisplay(Static):
    time_left = reactive(FLOW_POLL_SECONDS)
    def on_mount(self): self.set_interval(1.0, self.tick)
    def tick(self): 
        if self.time_left > 0: self.time_left -= 1
        self.update(Text.from_markup(f"[dim]Next Scan:[/] [bold cyan]{self.time_left:3d}s[/]", justify="right"))

class SPXProfilerNexusV21(App):
    CSS = """
    /* --- CRITICAL FIX: Force App to Fill Terminal --- */
    Screen { layout: vertical; background: $surface; width: 100%; height: 100%; }

    /* Header & Alert Area */
    #header { layout: horizontal; height: 5; background: $surface-darken-1; border-bottom: solid $primary; }
    InfoBox { width: 85%; height: 100%; layout: horizontal; } 
    #info_lbl { width: 1fr; height: 100%; content-align: left middle; }
    #btn_row { width: auto; height: 100%; align-vertical: middle; margin-right: 1; }
    
    StatusDisplay { width: 15%; height: 100%; content-align: right top; padding: 1; }
    #alerts { height: auto; min-height: 3; text-align: center; padding: 1; background: $secondary-darken-2; } #alerts.active { border-top: solid $warning; }
    
    /* MAIN LAYOUT */
    #main-container { width: 100%; height: 1fr; layout: horizontal; }
    #left-column { width: 30%; height: 100%; layout: vertical; }
    FlowBox { width: 100%; height: 100%; }
    #right-column { width: 70%; height: 100%; }
    WeeklyGexTable { width: 100%; height: 100%; }
    
    #cd { dock: bottom; height: 1; background: $primary; color: black; text-align: center; } 
    """
    scan_timer = reactive(FLOW_POLL_SECONDS) 
    last_gex_fetch = 0
    cached_gex_stats = []
    cached_orats_raw = []
    cached_dates = []
    current_data = []; ctx = {}; auto_snapshot_taken = False 

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"): yield InfoBox(id="info"); yield StatusDisplay(id="status")
        yield AlertBox(id="alerts"); 
        with Container(id="main-container"):
            with Container(id="left-column"):
                yield FlowBox(id="flow-box")
            with Container(id="right-column"):
                yield WeeklyGexTable(id="gex-table")
        yield Footer()

    async def on_mount(self):
        global ZMQ_FLOW_STATUS
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=get_ssl_context()))
        self.zmq_ctx = zmq.asyncio.Context()
        self.flow_pub_sock = self.zmq_ctx.socket(zmq.PUB)
        self.flow_pub_sock.setsockopt(zmq.LINGER, 0)
        
        log_debug(f"DEBUG: STARTUP @ {get_now_et()}")
        
        # [FIX] Retry Binding to handle TIME_WAIT from restarts
        for i in range(5):
            try:
                self.flow_pub_sock.bind(f"tcp://127.0.0.1:{PROFILER_FLOW_PORT}")
                ZMQ_FLOW_STATUS = "CONNECTED"
                break
            except zmq.ZMQError:
                ZMQ_FLOW_STATUS = f"RETRYING BIND ({i+1}/5)..."
                await asyncio.sleep(1)
        else:
            ZMQ_FLOW_STATUS = "FAILED TO BIND"

        self.query_one(AlertBox).update_alerts([])
        asyncio.create_task(stream_nexus())
        self.set_interval(1.0, self.tick); asyncio.create_task(self.run_scan())

    def tick(self):
        now = get_now_et()
        if now.minute == 0 and now.second < 5:
            if now.hour in SNAPSHOT_HOURS:
                if not self.auto_snapshot_taken:
                    self.on_snapshot()
                    self.auto_snapshot_taken = True
                    self.notify(f"Auto-Snapshot Taken ({now.hour}:00)")
        else:
            self.auto_snapshot_taken = False

        if self.scan_timer>0: self.scan_timer-=1; self.query_one(StatusDisplay).time_left = self.scan_timer
        else: asyncio.create_task(self.run_scan())

    async def run_scan(self):
        # [NEW] Dynamic Polling Interval (Matches user request: 3m during market, 5m off-hours)
        now = get_now_et()
        is_market_open = (
            now.weekday() < 5 and 
            (now.hour > 9 or (now.hour == 9 and now.minute >= 30)) and 
            (now.hour < 16)
        )
        
        # Poll 180s (3m) during market, 300s (5m) off-hours
        current_poll_interval = 180 if is_market_open else 300
        
        self.scan_timer = current_poll_interval
        self.notify(f"Scanning Flow (Interval: {current_poll_interval}s)...")
        
        # [FIX] GEX Sync: Always fetch GEX when Flow runs (Sync 3m/5m)
        # User requested 3m updates for EVERYTHING during market.
        should_fetch_gex = True 
        
        if should_fetch_gex:
            self.notify("Fetching GEX (ORATS)...")
            # self.gex_timer = current_poll_interval # No longer needed if always true
        
        # 1. Fetch Flow & Simple Price (Conditional GEX)
        self.ctx, uw, orats_raw, gex_stats, dates = await fetch_combined_data(self.session, fetch_gex=should_fetch_gex)
        
        # [FIX] Update Cache if Fresh GEX Data Arrived
        if gex_stats:
            # Embed the evaluated date string inside each dict for external Streamlit parsing
            if dates and len(dates) == len(gex_stats):
                for i, st in enumerate(gex_stats):
                    st['date'] = str(dates[i])
            
            self.cached_gex_stats = gex_stats
            self.cached_dates = dates
            self.cached_orats_raw = orats_raw # [FIX] Cache the raw chain for OMAP
            # Persist to disk
            try:
                with open("nexus_gex_static.json", 'w') as f:
                    json.dump({'gex_profiles': gex_stats, 'spot': self.ctx['price']}, f, default=str)
            except: pass

        # 2. Load Decoupled Snapshot (ONLY IF CACHE EMPTY)
        snap = load_gex_snapshot()
        if snap:
             if 'gex_profiles' in snap and not self.cached_gex_stats:
                 log_debug("DEBUG: cache empty, loading snapshot from disk.")
                 self.cached_gex_stats = snap['gex_profiles']
                 try:
                     self.cached_dates = [datetime.datetime.strptime(p['date'], '%Y-%m-%d').date() for p in snap['gex_profiles']]
                 except: pass
                 
             if 'spot' in snap and snap['spot'] > 0: 
                 if self.ctx['price'] == 0: self.ctx['price'] = snap['spot']
        
        # [FIX] Use Cached ORATS if live is not fetching (conditional toggle)
        final_orats = self.cached_orats_raw if self.cached_orats_raw else (orats_raw if orats_raw else [])
        final_gex = self.cached_gex_stats
        final_dates = self.cached_dates if self.cached_dates else dates

        try:
            data, alerts = process(uw, final_orats, self.ctx); self.current_data = data 
            essential_flow = [{'sym': r['sym'], 'exp': r['exp'], 'dte': r['dte'], 'stk': r['stk'], 'type': r['type'], 'prem': r['prem'], 'sentiment_score': 1 if "BULL" in r['conf'] else (-1 if "BEAR" in r['conf'] else 0)} for r in data]
            await self.flow_pub_sock.send_multipart([b"SPX_FLOW", json.dumps(essential_flow).encode('utf-8')])
            
            self.query_one(AlertBox).update_alerts(alerts)
            self.query_one(WeeklyGexTable).update_content(final_dates, final_gex)
            
            # --- BUILD MOCK UW FLOW DATA FOR FLOWBOX ---
            call_prem_tot = 0; put_prem_tot = 0; strike_data = []
            for strike_item in final_orats:
                try:
                    c_vol = float(strike_item.get('callVolume', 0))
                    c_oi = float(strike_item.get('callOpenInterest', 0))
                    p_vol = float(strike_item.get('putVolume', 0))
                    p_oi = float(strike_item.get('putOpenInterest', 0))
                    
                    c_mid = (float(strike_item.get('callBidPrice', 0)) + float(strike_item.get('callAskPrice', 0))) / 2
                    p_mid = (float(strike_item.get('putBidPrice', 0)) + float(strike_item.get('putAskPrice', 0))) / 2
                    if c_mid == 0 and float(strike_item.get('callBid', 0)) > 0: c_mid = (float(strike_item.get('callBid', 0)) + float(strike_item.get('callAsk', 0))) / 2
                    if p_mid == 0 and float(strike_item.get('putBid', 0)) > 0: p_mid = (float(strike_item.get('putBid', 0)) + float(strike_item.get('putAsk', 0))) / 2

                    call_prem = c_vol * c_mid * 100; put_prem = p_vol * p_mid * 100
                    
                    # Near-Term Filter: Only track Support/Resistance strikes within 7 Days (Ignore LEAPS)
                    try:
                        exp = strike_item.get('expirDate')
                        if exp:
                            exp_date = datetime.datetime.strptime(exp, '%Y-%m-%d').date()
                            dte = (exp_date - datetime.datetime.now().date()).days
                            if dte <= 7:
                                strike_data.append({"strike": float(strike_item.get('strike')), "call_premium": call_prem, "put_premium": put_prem})
                    except: pass
                    
                    call_prem_tot += call_prem; put_prem_tot += put_prem
                except: pass
                
            top_c = max(strike_data, key=lambda x: x['call_premium']) if strike_data else None
            top_p = max(strike_data, key=lambda x: x['put_premium']) if strike_data else None
            
            # --- NEW ACCUMULATOR ---
            cum_net_prem, cum_net_delta = track_accumulated_premium(final_orats, "spx_premium_state.json")
            
            flow_data = {
                'strike_data': {'total_call_premium': call_prem_tot, 'total_put_premium': put_prem_tot, 'top_call_strike': top_c, 'top_put_strike': top_p},
                'delta_ticks': [{'net_premium': cum_net_prem, 'net_delta': cum_net_delta}], 
                'flow_z_score': 0.0
            }
            self.query_one(FlowBox).update_content(flow_data)
            
            def calc_net(rows):
                bull = 0; bear = 0; net = 0
                for r in rows:
                    val = r['prem']
                    if "BULL" in r['conf']: bull += val; net += val
                    elif "BEAR" in r['conf']: bear += val; net -= val
                    else: 
                        if r['edge'] > 0.5 or r.get('urgency',0) > 0.05: bull += val; net += val
                        elif r['edge'] < -0.5 or r.get('urgency',0) < -0.05: bear += val; net -= val
                return {"bull": bull, "bear": bear, "net": net}

            data_d0 = [r for r in data if r['dte'] <= SHORT_DTE_CUTOFF]; data_d1 = [r for r in data if r['dte'] > SHORT_DTE_CUTOFF]
            stats_d0 = calc_net(data_d0); stats_d1 = calc_net(data_d1)
            sent_d0 = score_profiler_data(data_d0); sent_d1 = score_profiler_data(data_d1)
            
            agg_d0 = {'net': stats_d0['net'], 'sent': sent_d0}; agg_d1 = {'net': stats_d1['net'], 'sent': sent_d1}
        except Exception as e:
            import traceback
            log_debug(f"CRITICAL ERROR in data processing: {e}")
            log_debug(traceback.format_exc())
            return
        
        # -- BRIDGE DUMP --
        valid_stats = final_gex[0] if final_gex else None
        
        spx_magnet = 0
        if valid_stats:
            spx_magnet = float(valid_stats.get('volume_poc_strike') or 0)
        
        self.query_one(InfoBox).update_data(self.ctx, agg_d0, agg_d1, float(CUMULATIVE_SENTIMENT), cum_net_prem, spx_magnet)
        
        if valid_stats:
            def get_w(k): return float(valid_stats.get(k) or 0)
            
            # Adapted for Worker Flat Structure
            spx_put_wall = get_w('short_gamma_wall_below')
            spx_call_wall = get_w('short_gamma_wall_above')
            magnet = get_w('volume_poc_strike')
            
            basis = CURRENT_BASIS if CURRENT_BASIS != 0 else (self.ctx['price'] - (LIVE_PRICE['SPY'] * 10) if (self.ctx['price'] > 0 and LIVE_PRICE['SPY'] > 0) else 0)
            spy_put_wall = (spx_put_wall - basis) / 10 if spx_put_wall > 0 else 0
            spy_call_wall = (spx_call_wall - basis) / 10 if spx_call_wall > 0 else 0
            spy_magnet = (magnet - basis) / 10 if magnet > 0 else 0
            
            levels = {
                "timestamp": datetime.datetime.now().isoformat(), 
                "spx_price": LIVE_PRICE.get('SPX', 0), 
                "spy_price": LIVE_PRICE.get('SPY', 0), 
                "current_basis": basis, 
                "put_wall": round(spy_put_wall, 2), 
                "call_wall": round(spy_call_wall, 2), 
                "vol_trigger": round(spy_magnet, 2), 
                "spx_put_wall": spx_put_wall, 
                "spx_call_wall": spx_call_wall,
                "iv_30d": self.ctx.get('iv30', 0.0)
            }
            # Save Levels separately (always useful if valid)
            with open(MARKET_LEVELS_FILE, "w") as f: json.dump(levels, f, indent=4)
            
            
        # [DEC] Decoupled Dump Logic (Always Run)
        spx_put = 0; spx_call = 0; max_pain = 0; zero_gamma = 0; magnet_s = 0; net_gex_val = 0
        gex_metrics = {"pc_ratio_volume": 0, "pc_ratio_oi": 0, "spot_gamma": 0}
        
        if valid_stats:
            spx_put = float(valid_stats.get('short_gamma_wall_below') or 0)
            spx_call = float(valid_stats.get('short_gamma_wall_above') or 0)
            max_pain = float(valid_stats.get('max_pain_strike') or 0)
            magnet_s = float(valid_stats.get('volume_poc_strike') or 0)
            zero_gamma = float(valid_stats.get('gex_flip_point') or 0)
            net_gex_val = float(valid_stats.get('total_gamma') or 0)
            gex_metrics = {
                "pc_ratio_volume": float(valid_stats.get('pc_ratio_volume') or 0),
                "pc_ratio_oi": float(valid_stats.get('pc_ratio_oi') or 0),
                "spot_gamma": float(valid_stats.get('spot_gamma') or 0)
            }
            
        current_state = {
            "script": "spx_profiler",
            "spx_price": self.ctx['price'],
            "net_gex": net_gex_val,
            "gex_structure": final_gex or [],
            "zero_gamma_level": zero_gamma,
            "major_levels": {"put": spx_put, "call": spx_call, "max_pain": max_pain, "magnet": magnet_s},
            "trajectory": self.ctx.get('trajectory', 'Analyzing...'),
            "flow_stats": {
                "d0_net": stats_d0['net'], 
                "d0_sent": sent_d0, 
                "d1_net": stats_d1['net'], 
                "d1_sent": sent_d1, 
                "daily_cum_sent": float(CUMULATIVE_SENTIMENT),
                "cum_net_prem": float(cum_net_prem),
                "cum_net_delta": float(cum_net_delta)
            },
            "gex_metrics": gex_metrics,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        antigravity_dump("nexus_spx_profile.json", current_state)
        # [NEW] Push to Supabase asynchronously
        asyncio.create_task(upload_json_to_supabase("nexus_profile", current_state, id_field="id", id_value="latest"))
        self.notify("Flow Data Updated!")

    @on(Button.Pressed, "#btn_snapshot")
    def on_snapshot(self):
        if not self.current_data: self.notify("No data to snapshot!", severity="error"); return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S"); save_dir = Path("snapshots"); save_dir.mkdir(exist_ok=True)
        csv_filename = save_dir / f"{timestamp}_flow.csv"; json_filename = save_dir / f"{timestamp}_context.json"
        def json_serializer(obj):
            if isinstance(obj, (datetime.date, datetime.datetime, pd.Timestamp)): return obj.isoformat()
            if hasattr(obj, 'item'): return obj.item()
            if hasattr(obj, 'tolist'): return obj.tolist()
            raise TypeError(f"Type {type(obj)} not serializable")
        try:
            df = pd.DataFrame(self.current_data)
            cols = ['sym', 'exp', 'dte', 'stk', 'type', 'side_tag', 'prem', 'vol', 'oi', 'edge', 'conf', 'win', 'delta', 'gamma', 'vega', 'theta', 'underlying_price']
            df = df[cols] if not df.empty else df
            df.to_csv(csv_filename, index=False)
            print(f"[PATCHED] Added 'delta' and greeks to {csv_filename} output.")
        except Exception as e: self.notify(f"CSV Save Failed: {e}", severity="error"); return
        try:
            context_data = {
                "timestamp": timestamp, "spot_price_spx": LIVE_PRICE.get('SPX', 0), "spot_price_spy": LIVE_PRICE.get('SPY', 0), "basis_spread": CURRENT_BASIS,
                "iv_rank": getattr(self, 'ctx', {}).get('iv_rank', 0), "gex_structure": self.cached_gex_stats, "walls": {}
            }
            if os.path.exists(MARKET_LEVELS_FILE):
                with open(MARKET_LEVELS_FILE, 'r') as f: context_data['walls'] = json.load(f)
            with open(json_filename, "w") as f: json.dump(context_data, f, indent=4, default=json_serializer)
            self.notify(f"Snapshot Saved: {timestamp}", severity="information")
        except Exception as e: self.notify(f"JSON Save Failed: {e}", severity="error")
        
    async def load_tape(self, sym):
        if not sym: return
        self.notify(f"Tape Disabled (Unusual Whales API Removed).")
        dt=self.query_one("#t_dt", DataTable)
        dt.clear()
        self.query_one(TapeView).update_summary(0,0,0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    app = SPXProfilerNexusV21()
    APP_INSTANCE = app
    try:
        load_persistence()
        print(f"[STARTUP] Sentiment Loaded: {CUMULATIVE_SENTIMENT}")
    except Exception as e:
        print(f"[STARTUP] Persistence Load Failed: {e}")
    app.run()
