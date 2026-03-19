import os
# FILE: spy_profiler_nexus_v2.py
from textual.app import App, ComposeResult
from textual.widgets import Footer, DataTable, Static, TabbedContent, TabPane, Input, Button
from textual.containers import Horizontal, Vertical, Container
from textual.reactive import reactive
from rich.text import Text
from textual import events, on, work
import asyncio, aiohttp, json, datetime, os, re, math, ssl
from datetime import timedelta
from collections import Counter, deque, defaultdict
from pathlib import Path
import pandas as pd
import numpy as np
import zmq, zmq.asyncio
import time 
import requests 
import signal
import sys 


try: 
    import pytz
    ET = pytz.timezone('US/Eastern')
except: 
    ET = datetime.timezone(datetime.timedelta(hours=-5))


# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"

# --- PORTS (FIXED) ---
PROFILER_FLOW_PORT = 5573 
SELECT_PORT = 5560  # <--- 5560 avoids conflict with SPX

# --- SWING MODE CONFIGURATION ---
MIN_DTE = 0          
MAX_DTE = 60          
SHORT_DTE_CUTOFF = 3 

MIN_PREM = 500000; TOP_N = 100
MIN_VOI = 1.0; THEO_TOL = 0.015; STOP_MULT = 1.8; TRADING_DAYS = 252
POLL_SECONDS = 300
AFTER_HOURS_POLL_SECONDS = 300

# --- GLOBAL STATE ---
PRICE_DATA = {TICKER: {'prev': None, 'curr': None}}
TABLE_COLS = ("EXPIRY", "DTE", "CONTRACT", "SIDE", "PREMIUM", "VOL", "OI", "V/OI", "P/C(Vol)", "P/C(OI)", "MKT($)", "THEO($)", "EDGE", "CONFIDENCE", "Z-SCORE", "BE($)", "WIN%")
ZMQ_FLOW_STATUS = "DISCONNECTED" 
APP_INSTANCE = None

# --- ACCUMULATION STATE ---
SEEN_TRADES = set()
CUMULATIVE_SENTIMENT = 0
CUMULATIVE_SENTIMENT = 0
LAST_RESET_DATE = None
STATE_FILE = "spy_sentiment_state.json"

def load_persistence():
    global SEEN_TRADES, CUMULATIVE_SENTIMENT, LAST_RESET_DATE
    today = get_active_trading_date()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                saved_state = json.load(f)
                if saved_state.get('date') == today.isoformat():
                    LAST_RESET_DATE = today
                    CUMULATIVE_SENTIMENT = saved_state.get('sentiment', 0)
                    SEEN_TRADES = set(saved_state.get('seen_trades', []))
                else:
                    print(f"[SENTIMENT] SPY State Stale ({saved_state.get('date')}). Resetting for {today.isoformat()}")
                    LAST_RESET_DATE = today
                    CUMULATIVE_SENTIMENT = 0
                    SEEN_TRADES = set()
        except Exception as e:
            print(f"[SENTIMENT] SPY Load Error: {e}")
            LAST_RESET_DATE = today
    else:
        LAST_RESET_DATE = today

def shutdown_handler(sig, frame):
    print(f"\n[!] Caught signal {sig}. Shutting down...")
    if APP_INSTANCE:
        try:
            APP_INSTANCE.exit()
        except: pass
    # Allow Textual to clean up, but force exit if needed after a delay
    # sys.exit(0) # Removing immediate exit to allow cleanup 

def log_status(message):
    """Appends a timestamped message to profiler_status.log"""
    try:
        with open("profiler_status.log", "a") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] {message}\n")
    except: pass 

# --- HELPERS ---
def get_ssl_context():
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE; return ctx
def get_active_trading_date():
    try: tz = pytz.timezone('US/Eastern'); now = datetime.datetime.now(tz)
    except: now = datetime.datetime.utcnow() - timedelta(hours=5)
    while now.weekday() >= 5: now -= timedelta(days=1)
    return now.date()
def is_market_open():
    try: tz = pytz.timezone('US/Eastern'); now = datetime.datetime.now(tz)
    except: now = datetime.datetime.utcnow() - timedelta(hours=5)
    return now.weekday() < 5 and (9, 30) <= (now.hour, now.minute) <= (16, 0)
    


def norm_cdf(x): return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0

def fmt_notional(value, show_plus=False):
    if value is None: return "N/A"
    val_abs = abs(value)
    if val_abs >= 1e9: s = f"${val_abs/1e9:.1f}B"
    elif val_abs >= 1e6: s = f"${val_abs/1e6:.1f}M"
    elif val_abs >= 1e3: s = f"${val_abs/1e3:.1f}K"
    else: s = f"${val_abs:.0f}"
    if value < 0: s = "-" + s
    elif value > 0 and show_plus: s = "+" + s
    elif value == 0: return "$0"
    return s

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

# --- INTELLIGENCE ENGINES ---
class StatsEngine:
    def __init__(self, window_size=2000):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.mean = 0.0; self.std = 0.0

    def process(self, value):
        self.history.append(value)
        if len(self.history) < 2: return 0.0
        vals = np.array(self.history)
        self.mean = np.mean(vals); self.std = np.std(vals)
        return (value - self.mean) / self.std if self.std > 0 else 0.0

STATS_ENGINE = StatsEngine()

def detect_spreads(trades):
    grouped = defaultdict(list)
    for i, t in enumerate(trades): grouped[t.get('executed_at') or t.get('timestamp')].append(i)
    
    spread_map = {}
    for ts, indices in grouped.items():
        if len(indices) < 2: continue
        legs = [trades[i] for i in indices]
        # Simple Vertical Spread Check: Same Exp, Same Type, Diff Strike, Opp Side
        if len(legs) == 2:
            l1, l2 = legs[0], legs[1]
            if (l1.get('exp') == l2.get('exp') and l1.get('type') == l2.get('type') and 
                l1.get('stk') != l2.get('stk')):
                # Check side logic if available, otherwise assume spread if close in time/params
                spread_map[indices[0]] = "VERTICAL SPREAD"
                spread_map[indices[1]] = "VERTICAL SPREAD"
    return spread_map

def calculate_gex_flip(orats_data, spot_price):
    if not orats_data or not spot_price: return None
    strikes = defaultdict(float)
    for r in orats_data:
        try:
            stk = float(r['strike']); g = float(r.get('gamma') or 0); oi = int(r.get('openInterest') or 0)
            if r['optionType'] == 'C': strikes[stk] += g * oi * 100 * spot_price
            else: strikes[stk] -= g * oi * 100 * spot_price
        except: pass
    
    net_gamma = sum(strikes.values())
    
    sorted_strikes = sorted(strikes.keys())
    flip_level = None
    for i in range(len(sorted_strikes)-1):
        s1 = sorted_strikes[i]; s2 = sorted_strikes[i+1]
        g1 = strikes[s1]; g2 = strikes[s2]
        if (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
            flip_level = s1 if abs(g1) < abs(g2) else s2
            break
            
    return flip_level, net_gamma

    return flip_level, net_gamma

# --- NEXUS LISTENER ---

# --- NEXUS LISTENER ---
async def stream_nexus_data():
    ctx = zmq.asyncio.Context()
    sock = ctx.socket(zmq.SUB)
    try:
        sock.connect("tcp://localhost:5555")
        sock.setsockopt_string(zmq.SUBSCRIBE, TICKER)
        while True:
            msg = await sock.recv_multipart()
            data = json.loads(msg[1])
            if "Last" in data: 
                PRICE_DATA[TICKER]['curr'] = float(data['Last'])
            await asyncio.sleep(0.01) # Yield to prevent CPU hogging
    except Exception as e:
        log_status(f"Stream Error: {e}")

# --- DATA FETCHING ---
async def fetch_orats_live(s):
    try:
        async with s.get("https://api.orats.io/datav2/live/strikes", params={'token': ORATS_API_KEY, 'ticker': TICKER}, timeout=30) as r:
            if r.status == 200: return (await r.json()).get('data', [])
    except: pass
    return []

async def fetch_main_data_parallel(s):
    t_date = get_active_trading_date()
    ctx = {'price': 0.0, 'iv30': 0.0, 'hv30': 0.0, 'iv_rank': 0.0, 'prev': 0.0}
    
    uw_params_short = {
        'ticker_symbol': TICKER, 'order': 'premium', 'order_direction': 'desc', 
        'limit': TOP_N, 'min_dte': MIN_DTE, 'max_dte': SHORT_DTE_CUTOFF, 'min_premium': MIN_PREM
    }
    uw_params_long = {
        'ticker_symbol': TICKER, 'order': 'premium', 'order_direction': 'desc', 
        'limit': TOP_N, 'min_dte': SHORT_DTE_CUTOFF + 1, 'max_dte': MAX_DTE, 'min_premium': MIN_PREM
    }

    # [UPDATED] Added fields to optimize payload and include rVol30 (HV30)
    orats_fields = "ticker,stockPrice,prevClose,iv30d,rVol30,impliedVol"
    
    tasks = [
        s.get("https://api.orats.io/datav2/live/summaries", params={'token': ORATS_API_KEY, 'ticker': TICKER, 'fields': orats_fields}, timeout=10),
        s.get(f"https://api.unusualwhales.com/api/stock/{TICKER}/iv-rank", headers={'Authorization': f'Bearer {UW_API_KEY}'}, timeout=10),
        s.get("https://api.unusualwhales.com/api/screener/option-contracts", headers={'Authorization': f'Bearer {UW_API_KEY}'}, params=uw_params_short, timeout=30),
        s.get("https://api.unusualwhales.com/api/screener/option-contracts", headers={'Authorization': f'Bearer {UW_API_KEY}'}, params=uw_params_long, timeout=30),
        fetch_orats_live(s)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    if not isinstance(results[0], Exception) and hasattr(results[0], 'status') and results[0].status == 200:
        d = (await results[0].json()).get('data',[{}])[0]
        ctx['price'] = float(d.get('stockPrice') or 0)
        ctx['iv30'] = float(d.get('iv30d') or d.get('impliedVol') or 0)
        ctx['hv30'] = float(d.get('rVol30') or 0) # Mapped rVol30 to hv30
        ctx['prev'] = float(d.get('prevClose') or 0)

    if not isinstance(results[1], Exception) and hasattr(results[1], 'status') and results[1].status == 200:
        d = (await results[1].json()).get('data',[]); ctx['iv_rank'] = float(d[-1].get('iv_rank_1y') or 0) if d else 0
    
    uw_data_short = (await results[2].json()).get('data', []) if not isinstance(results[2], Exception) and hasattr(results[2], 'status') and results[2].status == 200 else []
    uw_data_long = (await results[3].json()).get('data', []) if not isinstance(results[3], Exception) and hasattr(results[3], 'status') and results[3].status == 200 else []
    uw_data = uw_data_short + uw_data_long
    
    orats_data = results[4] if not isinstance(results[4], Exception) else []
    
    return ctx, uw_data, orats_data, t_date

async def fetch_contract_tape_opt(s, contract_id):
    try:
        async with s.get(f"https://api.unusualwhales.com/api/option-contract/{contract_id}/flow", headers={'Authorization': f'Bearer {UW_API_KEY}'}, timeout=15) as r:
            if r.status == 200: return (await r.json()).get('data', [])
    except: pass
    return []

def calculate_pc_ratios_and_vol(orats_data):
    exp_data = {} 
    for r in orats_data:
        try:
            exp = r.get('expirDate')
            if not exp: continue
            
            if exp not in exp_data:
                exp_data[exp] = {'puts_oi': 0, 'calls_oi': 0, 'puts_vol': 0, 'calls_vol': 0}
            
            if 'putOpenInterest' in r and 'callOpenInterest' in r:
                exp_data[exp]['puts_oi'] += int(r.get('putOpenInterest', 0))
                exp_data[exp]['calls_oi'] += int(r.get('callOpenInterest', 0))
                exp_data[exp]['puts_vol'] += int(r.get('putVolume', 0))
                exp_data[exp]['calls_vol'] += int(r.get('callVolume', 0))
            elif r.get('optionType') == 'P':
                exp_data[exp]['puts_oi'] += int(r.get('openInterest', 0))
                exp_data[exp]['puts_vol'] += int(r.get('volume', 0))
            elif r.get('optionType') == 'C':
                exp_data[exp]['calls_oi'] += int(r.get('openInterest', 0))
                exp_data[exp]['calls_vol'] += int(r.get('volume', 0))
        except: continue
            
    pc_oi_map = {}
    pc_vol_map = {}
    for exp, data in exp_data.items():
        pc_oi_map[exp] = data['puts_oi'] / data['calls_oi'] if data['calls_oi'] > 0 else 0.0
        pc_vol_map[exp] = data['puts_vol'] / data['calls_vol'] if data['calls_vol'] > 0 else 0.0
        
    return pc_oi_map, pc_vol_map

def score_profiler_data(contracts: list[dict]) -> dict:
    sentiment_score = 0
    total_premium = 0
    put_premium_by_strike = {}
    call_premium_by_strike = {}

    if not contracts: return {"sentiment_score": 0, "put_wall": 0, "call_wall": 0}

    try:
        total_premium = sum(float(c.get('prem', 0)) for c in contracts)
        if total_premium == 0: total_premium = 1
    except: total_premium = 1

    for contract in contracts:
        try:
            premium = float(contract.get('prem', 0.0))
            option_type = contract.get('type', 'N/A')
            strike = float(contract.get('stk', 0.0))

            if option_type == 'PUT': put_premium_by_strike[strike] = put_premium_by_strike.get(strike, 0) + premium
            elif option_type == 'CALL': call_premium_by_strike[strike] = call_premium_by_strike.get(strike, 0) + premium
            
            # Basic scoring for summary
            if "BULL" in contract.get('conf', ''): sentiment_score += 1
            elif "BEAR" in contract.get('conf', ''): sentiment_score -= 1
            
        except: pass

    put_wall_strike = max(put_premium_by_strike, key=put_premium_by_strike.get) if put_premium_by_strike else 0
    call_wall_strike = max(call_premium_by_strike, key=call_premium_by_strike.get) if call_premium_by_strike else 0

    return {"sentiment_score": sentiment_score, "put_wall": put_wall_strike, "call_wall": call_wall_strike}

# --- PROCESSOR ---
def process_data(uw, orats, t_date, ctx):
    spot = PRICE_DATA[TICKER]['curr'] or ctx['price']; iv = ctx['iv30']; omap = {}
    
    for r in orats:
        try:
            exp = r['expirDate']; stk = float(r['strike'])
            if 'smv' in r and 'optionType' in r:
                 omap[f"{exp}|{stk:.1f}|{r['optionType'][0].upper()}"] = float(r['smv'])
            else:
                 if 'callValue' in r: omap[f"{exp}|{stk:.1f}|C"] = float(r['callValue'])
                 if 'putValue' in r:  omap[f"{exp}|{stk:.1f}|P"] = float(r['putValue'])
        except: pass

    pc_oi_map, pc_vol_map = calculate_pc_ratios_and_vol(orats)
    gex_flip, net_gamma = calculate_gex_flip(orats, spot) or (None, 0)
    spread_map = detect_spreads(uw)
    
    res = []; alerts = []; smart_bull_prem = 0; smart_bear_prem = 0
    
    for i, t in enumerate(uw):
        try:
            vol = int(t.get('volume') or 0); oi = int(t.get('open_interest') or 0)
            voi_ratio = (vol / (oi if oi > 0 else 1))
            if voi_ratio <= 1.0: continue
            
            # --- IV RANGE FILTER (30-Day Implied Move) ---
            # Range = Spot * IV30 * sqrt(30/365)
            # Sync to 1.0x Standard Deviation as requested for consistency with SPX/Sweeps
            if spot > 0 and iv > 0:
                im = spot * iv * math.sqrt(30.0 / 365.0)
                upper = spot + im
                lower = spot - im
                # Extract strike from option_symbol if not yet parsed (it is parsed below, let's parse early)
                # Optimization: We need to parse strike to filter. 
                # The existing code parses it a few lines down. Let's move parsing UP.
                sym = t.get('option_symbol',''); m = re.search(r'(\d{2})(\d{2})(\d{2})([CP])(\d{8})$', sym)
                if not m: continue
                yy,mm,dd,tc,sr = m.groups(); stk=float(sr)/1000
                
                if stk < lower or stk > upper: continue
            else:
                 # Standard parsing if filter skipped
                 sym = t.get('option_symbol',''); m = re.search(r'(\d{2})(\d{2})(\d{2})([CP])(\d{8})$', sym)
                 if not m: continue
                 yy,mm,dd,tc,sr = m.groups(); stk=float(sr)/1000

            exp=f"20{yy}-{mm}-{dd}"; otype='C' if tc=='C' else 'P'
            dte = max(0, (datetime.datetime.strptime(exp,"%Y-%m-%d").date()-t_date).days)
            
            mkt = float(t.get('close') or (float(t.get('bid')or 0)+float(t.get('ask')or 0))/2)
            theo = omap.get(f"{exp}|{stk:.1f}|{tc}", 0.0); edge = 0.0; val_score = 0
            if theo > 0:
                edge = ((theo - mkt) / theo) * 100
                if edge > 2.0: val_score = 1   
                elif edge < -2.0: val_score = -1 

            ask_vol = int(t.get('ask_side_volume') or 0); bid_vol = int(t.get('bid_side_volume') or 0)
            urgency = (ask_vol - bid_vol) / (vol or 1)
            if otype == 'P': urgency = -urgency 

            conf_score = 0
            if urgency > 0.2: conf_score += 1
            if val_score == 1: conf_score += 1 
            if voi_ratio > 3.0: conf_score += 1 
            
            if urgency < -0.2: conf_score -= 1
            if val_score == -1: conf_score -= 1 

            if conf_score >= 2: conf = "🟢 BULL"
            elif conf_score <= -2: conf = "🔴 BEAR"
            else: conf = "⚪ NEUTRAL"

            prem = float(t.get('premium') or 0)
            z_score = STATS_ENGINE.process(prem)
            
            spread_type = spread_map.get(i)
            if spread_type:
                conf = "⚪ HEDGE"
                # Optional: Adjust sentiment score logic for spreads if needed
            
            is_ml = vol > 0 and (int(t.get('multileg_volume') or 0) / vol) > 0.3
            
            win_pct = 50.0
            be = stk + mkt if otype == 'C' else stk - mkt
            if spot > 0 and iv > 0 and dte > 0:
                z = math.log(be / spot) / (iv * math.sqrt(dte / 365.0))
                win_pct = (1.0 - norm_cdf(z)) * 100 if otype == 'C' else norm_cdf(z) * 100
            elif dte == 0:
                 if (otype=='C' and spot>stk) or (otype=='P' and spot<stk): win_pct=100.0
                 else: win_pct=0.0

            # [PATCHED] Added 'delta' and 'gamma' capture
            delta = float(t.get('greeks', {}).get('delta') or t.get('delta') or 0.0)

            # --- ACCUMULATION LOGIC (WITH ROBUST PERSISTENCE) ---
            global SEEN_TRADES, CUMULATIVE_SENTIMENT, LAST_RESET_DATE
            today = get_active_trading_date()
            
            # Initial Load (Fallback)
            if LAST_RESET_DATE is None:
                load_persistence()

            # Daily Reset Check
            if LAST_RESET_DATE != today:
                print(f"[SENTIMENT] NEW DAY DETECTED (SPY). Resetting Score (Old: {CUMULATIVE_SENTIMENT})")
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
                tr_sig = f"{sym}_{t.get('timestamp')}_{prem}"
                tr_id = hash(tr_sig)
                
            if tr_id not in SEEN_TRADES:
                 # [FIX] ROBUST TIMEZONE-AWARE DATE CHECK
                 try:
                     ts_str = t.get('timestamp', '')
                     # Handle Z/ISO
                     if ts_str.endswith('Z'): dt_utc = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                     else: dt_utc = datetime.datetime.fromisoformat(ts_str)
                     
                     dt_et = dt_utc.astimezone(ET)
                     
                     if dt_et.date().isoformat() == today.isoformat():
                         # Calculate Score Contribution
                         score_contrib = 0
                         if "BULL" in conf: score_contrib = 1
                         elif "BEAR" in conf: score_contrib = -1
                         
                         if score_contrib != 0:
                             CUMULATIVE_SENTIMENT += score_contrib
                             SEEN_TRADES.add(tr_id)
                             # print(f"[SENTIMENT] SPY Trade {tr_id} ({conf}) -> Score: {CUMULATIVE_SENTIMENT}")
                             
                             # SAVE STATE IMMEDIATELY
                             try:
                                 with open(STATE_FILE, 'w') as f:
                                     json.dump({'date': today.isoformat(), 'sentiment': CUMULATIVE_SENTIMENT, 'seen_trades': list(SEEN_TRADES)}, f)
                             except: pass
                             
                 except Exception as e: pass
                 SEEN_TRADES.add(tr_id)
            tr_id = t.get('id')
            if not tr_id:
                tr_sig = f"{sym}_{t.get('timestamp')}_{prem}_{vol}"
                tr_id = hash(tr_sig)
                
            if tr_id not in SEEN_TRADES:
                # [FIX] ROBUST TIMEZONE-AWARE DATE CHECK (UTC -> ET)
                try:
                    ts_str = t.get('timestamp', '')
                    if ts_str.endswith('Z'): dt_utc = datetime.datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    else: dt_utc = datetime.datetime.fromisoformat(ts_str)
                    
                    # Use Global ET (Safe)
                    dt_et = dt_utc.astimezone(ET)
                    
                    if dt_et.date().isoformat() == today.isoformat():
                        # Calculate Score Contribution
                        score_contrib = 0
                        if "BULL" in conf: score_contrib = 1
                        elif "BEAR" in conf: score_contrib = -1
                        
                        if abs(conf_score) >= 3: score_contrib *= 2
                        
                        if score_contrib != 0:
                            old_score = CUMULATIVE_SENTIMENT
                            CUMULATIVE_SENTIMENT += score_contrib
                            SEEN_TRADES.add(tr_id)
                            # print(f"[SENTIMENT] SPY Trade {tr_id} -> Score: {old_score} -> {CUMULATIVE_SENTIMENT}")
                except Exception as e:
                    pass
                
                SEEN_TRADES.add(tr_id)

            gamma = float(t.get('greeks', {}).get('gamma') or t.get('gamma') or 0.0)
            vega = float(t.get('greeks', {}).get('vega') or t.get('vega') or 0.0)
            theta = float(t.get('greeks', {}).get('theta') or t.get('theta') or 0.0)

            # --- SIDE CALC ---
            side_str = "MID"
            if urgency > 0.05: side_str = "BOT"
            elif urgency < -0.05: side_str = "SOLD"
            
            if side_str == "MID": continue
            elif urgency < -0.05: side_str = "SOLD"

            res.append({
                'symbol': sym, 'exp':exp, 'dte':dte, 'stk':stk, 
                'type':'CALL' if otype=='C' else 'PUT', 'side': side_str,
                'prem': prem, 'vol':vol, 'oi':oi, 
                'delta': delta, 'gamma': gamma, 'vega': vega, 'theta': theta, # Added to result
                'voi_ratio': voi_ratio, 
                'pc_ratio_oi': pc_oi_map.get(exp, 0), 
                'pc_ratio_vol': pc_vol_map.get(exp, 0), 
                'mkt':mkt, 'theo':theo, 'edge':edge, 
                'conf':conf, 'be':be, 'win':win_pct, 'is_ml': is_ml,
                'z_score': z_score, 'spread_type': spread_type,
                'z_score': z_score, 'spread_type': spread_type,
                'delta': delta, 'gamma': gamma, 'underlying_price': spot
            })

        except: continue
        
    # [PERSISTENCE] Safe Save State
    if LAST_RESET_DATE == get_active_trading_date():
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

    return sorted(res, key=lambda x:x['prem'], reverse=True), {'gex_flip': gex_flip, 'net_gamma': net_gamma}, alerts[:5], len(uw), len(orats)

def format_row_data(r):
    voi = r['voi_ratio']
    prem_str = fmt_notional(r['prem'])
    edge_txt = Text(f"{r['edge']:+.1f}%", style="bold green" if r['edge'] > 1.5 else ("bold red" if r['edge'] < -1.5 else "dim white"))
    
    voi_style = "bold yellow"
    if voi >= 10: voi_style = "bold on yellow"
    elif voi < 1: voi_style = "dim white"
    
    pc_vol = r['pc_ratio_vol']
    pc_vol_style = "bold red" if pc_vol > 0.9 else ("bold green" if pc_vol < 0.7 else "white")
    
    z_score = r.get('z_score', 0.0)
    z_str = Text(f"{z_score:.1f}σ", style="bold magenta" if abs(z_score) > 3.0 else "dim white")
    conf_base = r['conf'].replace('🟢 ','').replace('🔴 ','').replace('⚪ ','')
    
    return (r['exp'], str(r['dte']), Text(f"${r['stk']:.0f} {r['type']}{' Ⓜ️' if r['is_ml'] else ''}", style="bold green" if r['type']=='CALL' else "bold red"), 
            Text(r['side'], style="bold green" if r['side']=="BOT" else ("bold red" if r['side']=="SOLD" else "dim white")),
            prem_str, str(r['vol']), str(r['oi']), Text(f"{voi:.1f}x" if r['oi']>0 else "NEW", style=voi_style), 
            Text(f"{pc_vol:.2f}", style=pc_vol_style), 
            Text(f"{r['pc_ratio_oi']:.2f}", style="dim"), 
            f"{r['mkt']:.2f}", f"{r['theo']:.2f}", edge_txt, 
            Text(conf_base, style="green" if "BULL" in r['conf'] else ("red" if "BEAR" in r['conf'] else "white")), 
            z_str,
            f"{r['be']:.2f}", 
            Text(f"{r['win']:.0f}%", style="green" if r['win']>60 else ("red" if r['win']<40 else "white")) if r['win']!=-1 else "-")

# --- WIDGETS ---
class AlertDisplay(Static):
    def update_alerts(self, alerts):
        self.styles.height = len(alerts) + 1 if alerts else 0
        self.update(Text.from_markup("[bold blink white on red] 🚨 SMART MONEY ALERTS 🚨 [/]\n" + "\n".join(alerts)) if alerts else "")

class InfoDisplay(Container):
    def compose(self) -> ComposeResult:
        yield Static(id="info_lbl")
        with Horizontal(id="btn_row"):
            yield Button("REFRESH", id="btn_refresh", variant="primary")
            yield Button("SNAPSHOT", id="btn_snapshot", variant="warning")

    # --- RESTORED FULL DISPLAY LOGIC ---
    def update_stats(self, ctx, agg_d0, analysis_d0, agg_d1, analysis_d1, gex_flip=None, daily_cum_sent=0):
        p = PRICE_DATA[TICKER]['curr'] or ctx.get('price', 0); prev = ctx.get('prev', 0)
        chg = ((p - prev) / prev) * 100 if prev > 0 else 0
        iv30 = ctx.get('iv30', 0.0)
        
        em_7d = p * iv30 * math.sqrt(7 / 365.0) if p > 0 and iv30 > 0 else 0.0
        
        # [NEW] Range Display
        range_str = ""
        if p > 0 and iv30 > 0:
            imp = p * iv30 * math.sqrt(30.0/365.0)
            range_str = f" | [bold cyan]Range: {p-imp:.2f}-{p+imp:.2f} (IV:{iv30:.1%})[/]"

        price_str = f"{TICKER}: [bold]${p:.2f}[/] ([{'green' if chg>=0 else 'red'}]{chg:+.2f}%[/])"
        flip_str = f" | Flip: [cyan]${gex_flip:.0f}[/]" if gex_flip else ""
        iv_str = f"IV30: {iv30*100:.1f}%{range_str} | EM (7D): [yellow]${em_7d:.2f}[/]{flip_str}"
        
        score_style_d0 = "bold green" if agg_d0.get('net_val',0) > 0 else "white" # Not used for logic, simplified
        flow_d0_str = f"Setup Flow ({MIN_DTE}-{SHORT_DTE_CUTOFF}d): {agg_d0.get('net_label','-')}"

        score_style_d1 = "bold green" if agg_d1.get('net_val',0) > 0 else "white" # Not used
        flow_d1_str = f"Target Flow ({SHORT_DTE_CUTOFF}+d): {agg_d1.get('net_label','-')}"

        # [NEW] Daily Tally
        sent_style = "bold green" if daily_cum_sent > 0 else ("bold red" if daily_cum_sent < 0 else "white")
        daily_sent_str = f"Daily Sentiment: [{sent_style}]{daily_cum_sent:+d}[/]"

        # [FIX] Trust usage of variable, verify via log
        status_color = "green" if ZMQ_FLOW_STATUS == "CONNECTED" else ("red" if "FAIL" in ZMQ_FLOW_STATUS else "yellow")
        status_str = f"ZMQ: [{status_color}]● {ZMQ_FLOW_STATUS}[/]"

        self.query_one("#info_lbl", Static).update(Text.from_markup(
            f"{price_str} | {iv_str}\n"
            f"{flow_d0_str} | {flow_d1_str} | {daily_sent_str} | {status_str}"
        ))

class StatusDisplay(Static):
    time_left = reactive(POLL_SECONDS)
    def on_mount(self): self.set_interval(1.0, self.tick)
    def tick(self): 
        if self.time_left > 0: self.time_left -= 1
        self.update(Text.from_markup(f"[dim]Next Scan:[/] [bold cyan]{self.time_left:3d}s[/] | [{'green' if is_market_open() else 'red'}]●[/]", justify="right"))

class TapeAnalyzer(Vertical):
    def compose(self) -> ComposeResult:
        yield DataTable(id="contract_header"); yield Static("Waiting...", id="tape_summary")
        with Horizontal(classes="tape_controls"): yield Input(placeholder="Contract...", id="tape_input"); yield Button("LOAD", id="tape_load_btn", variant="primary")
        yield DataTable(id="tape_table")
    def on_mount(self):
        self.query_one("#contract_header", DataTable).add_columns(*TABLE_COLS); self.query_one("#contract_header", DataTable).cursor_type="none"; self.query_one("#contract_header", DataTable).styles.height=3
        self.query_one("#tape_table", DataTable).add_columns("TIME (ET)", "SIDE", "PRICE", "SIZE", "FLAGS"); self.query_one("#tape_table", DataTable).cursor_type="row"
    def update_header(self, r): self.query_one("#contract_header", DataTable).clear(); self.query_one("#contract_header", DataTable).add_row(*format_row_data(r))
    def update_summary(self, bp, sp, net): self.query_one("#tape_summary", Static).update(Text.from_markup(f"BUY: [green]{fmt_notional(bp)}[/] | SELL: [red]{fmt_notional(sp)}[/] | NET: [{'green' if net>0 else 'red'}]{fmt_notional(net, show_plus=True)}[/]"))

class SpyProfilerNexusV8(App):
    CSS = """
    #header_container { dock: top; height: 5; background: $surface-darken-1; border-bottom: solid $primary; }
    AlertDisplay { dock: top; height: 0; background: $error-darken-2; text-align: center; }
    InfoDisplay { width: 70%; height: 100%; layout: horizontal; align-vertical: middle; padding-left: 1; }
    #info_lbl { width: 1fr; height: 100%; content-align: left middle; }
    #btn_snapshot { width: 12; margin-left: 1; margin-right: 1; }
    StatusDisplay { width: 30%; height: 100%; content-align: right top; padding-right: 1; }
    TabbedContent { height: 1fr; } 
    DataTable { height: 1fr; }
    #tape_input { width: 80%; } #tape_load_btn { width: 20%; } .tape_controls { height: 3; }
    #contract_header { height: 3; background: $surface-darken-1; }
    #tape_summary { height: 3; content-align: center middle; background: $surface-darken-2; }
    """
    current_data = []
    last_ctx = {'price':0,'iv30':0,'prev':0}
    last_agg_d0 = {}; last_agg_d1 = {}; last_market_analysis_d0 = {}; last_market_analysis_d1 = {}
    last_gex_flip = None

    def compose(self) -> ComposeResult:
        yield AlertDisplay()
        with Horizontal(id="header_container"): yield InfoDisplay(); yield StatusDisplay()
        with TabbedContent(initial="d0", id="main_tabs"):
            with TabPane(f"{MIN_DTE}-{SHORT_DTE_CUTOFF} DTE (Setup)", id="d0"): yield DataTable(id="dt0")
            with TabPane(f"{SHORT_DTE_CUTOFF}+ DTE (Target)", id="d1"): yield DataTable(id="dt1")
            with TabPane("Tape", id="tape"): yield TapeAnalyzer()
        yield Footer()

    @on(Button.Pressed, "#btn_refresh")
    def on_manual_refresh(self):
        self.notify("Manual Refresh Triggered")
        self.query_one(StatusDisplay).time_left = 1 # Tick down immediately
        asyncio.create_task(self.action_refresh())

    async def on_mount(self):
        global ZMQ_FLOW_STATUS
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=get_ssl_context()))
        self.zmq_ctx = zmq.asyncio.Context()
        
        # --- BIND SELECT SOCKET ---
        # --- BIND SELECT SOCKET ---
        self.select_sock = self.zmq_ctx.socket(zmq.PUB)
        self.select_sock.setsockopt(zmq.LINGER, 0)
        try:
            self.select_sock.bind(f"tcp://127.0.0.1:{SELECT_PORT}") 
        except zmq.ZMQError as e:
            self.notify(f"Select Sock Bind Failed: {e}", severity="error")
            # Retry Select as well
            for _ in range(10):
                try: 
                    time.sleep(1)
                    self.select_sock.bind(f"tcp://127.0.0.1:{SELECT_PORT}")
                    break
                except: pass
        
        self.flow_pub_sock = self.zmq_ctx.socket(zmq.PUB)
        self.flow_pub_sock.setsockopt(zmq.LINGER, 0)
        
        # [FIX] Retry Binding for SPY Profiler (Extended)
        for i in range(15):
            try:
                self.flow_pub_sock.bind(f"tcp://127.0.0.1:{PROFILER_FLOW_PORT}")
                ZMQ_FLOW_STATUS = "CONNECTED"
                log_status("ZMQ Flow Connected.")
                break
            except zmq.ZMQError as e:
                ZMQ_FLOW_STATUS = f"RETRYING ({i+1}/15)..."
                log_status(f"ZMQ Bind Retry {i+1}: {e}")
                await asyncio.sleep(1)
        else:
            ZMQ_FLOW_STATUS = "FAILED TO BIND"
            log_status("ZMQ Bind GAVE UP.")

        for table_id in ["#dt0", "#dt1"]:
            dt = self.query_one(table_id, DataTable)
            dt.add_columns(*TABLE_COLS)
            dt.cursor_type = "row"        
        
        # Fixed duplicate task creation
        asyncio.create_task(stream_nexus_data())
        # asyncio.create_task(stream_nexus_data()) # REMOVED DUPLICATE
        asyncio.create_task(self.action_refresh())
        self.set_interval(1.0, self.fast_tick)

    def schedule_next_scan(self):
        delay = POLL_SECONDS
        if not is_market_open():
            delay = AFTER_HOURS_POLL_SECONDS
            self.notify(f"Entering Eco-Mode ({delay}s delay)...")
        
        self.set_timer(delay, self.action_refresh)

    async def on_unmount(self): 
        await self.session.close()
        if hasattr(self, 'zmq_ctx'):
            self.zmq_ctx.term()
            
    def fast_tick(self): 
        self.query_one(InfoDisplay).update_stats(
            self.last_ctx, self.last_agg_d0, self.last_market_analysis_d0, self.last_agg_d1, self.last_market_analysis_d1, self.last_gex_flip, int(CUMULATIVE_SENTIMENT)
        )

    async def action_refresh(self):
        delay = POLL_SECONDS # Always use standard poll
        self.query_one(StatusDisplay).time_left = delay
        self.notify("Scanning...")
        log_status("Starting Scan...")
        
        try:
            ctx, uw, orats, t_date = await fetch_main_data_parallel(self.session)
            log_status(f"Data Fetched. UW: {len(uw)} items.")
            self.current_data, global_analysis, alerts, uw_c, orats_c = process_data(uw, orats, t_date, ctx)
            self.last_ctx = ctx 
            self.last_gex_flip = global_analysis.get('gex_flip') 
            
            self.last_ctx = ctx 
            self.last_gex_flip = global_analysis.get('gex_flip') 
            
            # --- VRP TOOL (Injection) ---
            # Added per User Request: VRP Spread = iv30d - hv30 (rVol30)
            try:
                iv30 = ctx.get('iv30', 0)
                hv30 = ctx.get('hv30', 0)
                vrp = iv30 - hv30
                
                log_status(f"NB: VRP Calculation -> IV30:{iv30:.4f}, HV30:{hv30:.4f}, Spread:{vrp:.4f}")
                
                vrp_data = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "ticker": TICKER,
                    "iv30": iv30,
                    "hv30": hv30,
                    "vrp_spread": vrp,
                    "signal": "SELL_PREMIUM" if vrp > 0 else "BUY_PREMIUM"
                }
                
                # Check current dir
                cwd = os.getcwd()
                log_status(f"Dumping VRP to {cwd}/nexus_vrp_context.json")
                
                antigravity_dump("nexus_vrp_context.json", vrp_data)
                
            except Exception as e:
                log_status(f"VRP Calc Error: {e}")

            data_d0 = [r for r in self.current_data if r['dte'] <= SHORT_DTE_CUTOFF]
            data_d1 = [r for r in self.current_data if r['dte'] > SHORT_DTE_CUTOFF]

            # --- NET FLOW FIX: INCLUDE NEUTRAL TRADES ---
            def calc_net(rows):
                total = 0
                for r in rows:
                    if "BULL" in r.get('conf',''): total += r['prem']
                    elif "BEAR" in r.get('conf',''): total -= r['prem']
                    else: 
                        # If Neutral, use Edge to determine lean so we don't return $0
                        total += r['prem'] if r.get('edge',0) > 0 else -r['prem']
                return total

            net_d0 = calc_net(data_d0)
            self.last_agg_d0 = {'net_label': f"[{'green' if net_d0>0 else 'red'}]{fmt_notional(net_d0, show_plus=True)}[/]"}
            self.last_market_analysis_d0 = score_profiler_data(data_d0)

            net_d1 = calc_net(data_d1)
            self.last_agg_d1 = {'net_label': f"[{'green' if net_d1>0 else 'red'}]{fmt_notional(net_d1, show_plus=True)}[/]"}
            self.last_market_analysis_d1 = score_profiler_data(data_d1)

            try:
                spy_price = PRICE_DATA[TICKER]['curr'] or ctx.get('price', 0)
                
                # Extract Walls
                p_wall = self.last_market_analysis_d1.get("put_wall", 0)
                c_wall = self.last_market_analysis_d1.get("call_wall", 0)
                
                # Existing Dump (Keep it as requested)
                # [DISABLED] CONFLICT: This script was overwriting the master market_levels.json
                # generated by spx_profiler_nexus.py, causing data loss (missing IV30).
                # levels_data = {
                #     "spy_price": spy_price,
                #     "put_wall": p_wall, 
                #     "call_wall": c_wall 
                # }
                # with open(temp_file, "w") as f: json.dump(levels_data, f)
                # os.rename(temp_file, target_file)

                # --- ANTIGRAVITY DEEP FLOW DUMP ---
                # Logic for Accumulation/Distribution
                prev_close = ctx.get('prev', 0)
                pct_change = (spy_price - prev_close) / prev_close if prev_close > 0 else 0
                flow_vol = len(uw)
                
                accumulation = flow_vol > 50 and abs(pct_change) < 0.001
                distribution = flow_vol > 50 and pct_change < -0.002
                
                current_flow_state = {
                    "script": "spy_profiler_deep_dive",
                    "flow_sentiment": {
                        "0dte_flow": float(net_d0),
                        "0dte_sent": self.last_market_analysis_d0.get('sentiment_score', 0),
                        "next_expiry_bias": float(net_d1),
                        "next_expiry_sent": self.last_market_analysis_d1.get('sentiment_score', 0),
                        "daily_cum_sent": int(CUMULATIVE_SENTIMENT)
                    },
                    "structure_details": {
                        "top_call_strike": c_wall,
                        "top_put_strike": p_wall,
                        "gamma_flip_level": self.last_gex_flip
                    },
                    "divergence_signals": {
                        "accumulation_detected": accumulation,
                        "distribution_detected": distribution
                    },
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }
                antigravity_dump("nexus_spy_flow_details.json", current_flow_state)
                log_status(f"Deep Flow Dumped. 0DTE: {net_d0}")

            except Exception as e:
                self.notify(f"JSON Write Err: {e}", severity="error")
                log_status(f"JSON Write Error: {e}")

            t_d0 = self.query_one("#dt0", DataTable); t_d0.clear()
            for r in data_d0: 
                if r.get('symbol'): t_d0.add_row(*format_row_data(r), key=r['symbol'])

            t_d1 = self.query_one("#dt1", DataTable); t_d1.clear()
            for r in data_d1: 
                if r.get('symbol'): t_d1.add_row(*format_row_data(r), key=r['symbol'])

            self.notify(f"Updated: {len(data_d0)}/{len(data_d1)}")

        except Exception as e: 
            self.notify(f"Refresh Err: {e}", severity="error")
            log_status(f"Refresh Error: {e}")
        finally:
            self.schedule_next_scan()

    @on(DataTable.RowSelected, "#dt0, #dt1")
    def on_row(self, event):    
        try: 
            r = next(item for item in self.current_data if item['symbol'] == event.row_key.value)
            self.query_one("#main_tabs", TabbedContent).active="tape"
            self.query_one(TapeAnalyzer).update_header(r)
            self.query_one("#tape_input", Input).value=r['symbol']
            asyncio.create_task(self.load_tape(r['symbol']))

            # --- SEND DATA TO DASHBOARD ---
            msg = json.dumps(r)
            self.select_sock.send_multipart([b"SELECT", msg.encode('utf-8')])
            self.notify(f"Sent {r['symbol']} to Dashboard")

        except Exception as e: 
            self.notify(f"Select Error: {e}", severity="error")
            
    @on(Button.Pressed, "#tape_load_btn")
    def on_tape_click(self): 
        asyncio.create_task(self.load_tape(self.query_one("#tape_input", Input).value))

    # --- SNAPSHOT FUNCTIONALITY ---
    @on(Button.Pressed, "#btn_snapshot")
    def on_snapshot(self):
        if not self.current_data:
            self.notify("No data to snapshot!", severity="error")
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_dir = Path("snapshots_spy")
        save_dir.mkdir(exist_ok=True)

        csv_filename = save_dir / f"{timestamp}_spy_flow.csv"
        json_filename = save_dir / f"{timestamp}_spy_context.json"

        def json_serializer(obj):
            if isinstance(obj, (datetime.date, datetime.datetime, pd.Timestamp)):
                return obj.isoformat()
            if hasattr(obj, 'item'): 
                return obj.item()
            if hasattr(obj, 'tolist'): 
                return obj.tolist()
            raise TypeError(f"Type {type(obj)} not serializable")

        try:
            df = pd.DataFrame(self.current_data)
            df = pd.DataFrame(self.current_data)
            cols_to_keep = ['symbol', 'exp', 'dte', 'stk', 'type', 'prem', 'vol', 'oi', 'voi_ratio', 'edge', 'conf', 'win', 'delta', 'gamma', 'underlying_price']
            existing_cols = [c for c in cols_to_keep if c in df.columns]
            df = df[existing_cols] if not df.empty else df
            df.to_csv(csv_filename, index=False)
            print(f"[PATCHED] Added 'delta' column to {csv_filename} output.")
        except Exception as e:
            self.notify(f"CSV Save Failed: {e}", severity="error")
            return

        try:
            spy_price = PRICE_DATA[TICKER]['curr'] or self.last_ctx.get('price', 0)
            context_data = {
                "timestamp": timestamp,
                "ticker": TICKER,
                "spot_price": spy_price,
                "iv30": self.last_ctx.get('iv30', 0),
                "iv_rank": self.last_ctx.get('iv_rank', 0),
                "analysis_setup_d0": self.last_market_analysis_d0,
                "analysis_target_d1": self.last_market_analysis_d1,
                "flow_net_setup": self.last_agg_d0.get('net_label', 'N/A'),
                "flow_net_target": self.last_agg_d1.get('net_label', 'N/A')
            }
            
            with open(json_filename, "w") as f:
                json.dump(context_data, f, indent=4, default=json_serializer)
            
            self.notify(f"Snapshot Saved: {timestamp}", severity="information")
        except Exception as e:
            self.notify(f"JSON Save Failed: {e}", severity="error")

    async def load_tape(self, sym):
        if not sym: return
        self.notify(f"Loading Tape for {sym}...")
        try:
            trades = await fetch_contract_tape_opt(self.session, sym)
            t = self.query_one("#tape_table", DataTable); t.clear()
            bp=0; sp=0
            trades.sort(key=lambda x: x.get('executed_at', ''))
            last_price = 0.0
            processed_rows = []
            
            for tr in trades:
                price = float(tr.get('price') or 0)
                size = int(tr.get('size') or 0)
                prem = float(tr.get('premium') or 0)
                tags = tr.get('tags') or []
                side = "MID"; style = "dim white"
                
                if 'ask_side' in tags: side = "BUY"; style = "bold green"
                elif 'bid_side' in tags: side = "SELL"; style = "bold red"
                else:
                    if last_price > 0:
                        if price > last_price: side = "BUY (Tick)"; style = "green"
                        elif price < last_price: side = "SELL (Tick)"; style = "red"
                
                if "BUY" in side: bp += prem
                if "SELL" in side: sp += prem
                last_price = price
                
                time_str = tr.get('executed_at', '').split('T')[1][:8] if 'T' in tr.get('executed_at', '') else '00:00:00'
                processed_rows.append([time_str, Text(side, style), f"${price:.2f}", str(size), ",".join(tags)])

            for row in reversed(processed_rows): t.add_row(*row)
            self.query_one(TapeAnalyzer).update_summary(bp, sp, bp-sp)
            self.notify("Tape Loaded")
        except Exception as e: self.notify(f"Tape Failed: {e}", severity="error")

if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)
    app = SpyProfilerNexusV8()
    APP_INSTANCE = app
    try:
        load_persistence()
        print(f"[STARTUP] SPY Sentiment Loaded: {CUMULATIVE_SENTIMENT}")
        app.run()
    except Exception as e:
        print(f"App Crashed: {e}")
    finally:
        print("Exiting...")
        shutdown_handler(0, None)