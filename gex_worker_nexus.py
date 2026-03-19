import asyncio
import aiohttp
import pandas as pd
import numpy as np
import datetime
import time
import json
import os
import sys
import requests
from scipy.stats import norm

# --- CONFIG ---
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")
ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TARGET_TICKER = "SPX"
POLL_INTERVAL = 900  # 15 Minutes
SNAPSHOT_FILE = "nexus_gex_static.json"
MARKET_LEVELS_FILE = "market_levels.json"

# --- UTILS ---
def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def get_trading_date():
    now = datetime.datetime.now()
    if now.hour >= 17: # After 5PM ET, use next day
        return (now + datetime.timedelta(days=1)).date()
    return now.date()

def get_next_n_trading_dates(start_date, n):
    dates = []
    current = start_date
    while len(dates) < n:
        if current.weekday() < 5: # Mon-Fri
            dates.append(current)
        current += datetime.timedelta(days=1)
    return dates

# --- GEX LOGIC ---
def analyze_gamma_exposure(strikes_data, spot_price, target_date_str):
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
        
        if df_target.empty: return summary_stats

        cols = ['gamma', 'callOpenInterest', 'putOpenInterest', 'callVolume', 'putVolume', 'strike']
        for c in cols: df_target[c] = pd.to_numeric(df_target[c], errors='coerce').fillna(0)
        
        call_gex = df_target['callOpenInterest'] * 100 * df_target['gamma']
        put_gex = (df_target['putOpenInterest'] * 100 * df_target['gamma'])
        total_gex_units = (call_gex - put_gex) 
        
        summary_stats['total_gamma'] = total_gex_units.sum() * (spot_price**2) * 0.01
        df_target['total_gamma_exp'] = total_gex_units * (spot_price**2) * 0.01
        
        if df_target['total_vol'].sum() > 0:
            # [FIX] POC Calculation: Use Notional Volume to filter out cheap OTM noise
            # Notional = Total Vol * Strike * 100
            df_target['notional_vol'] = df_target['total_vol'] * df_target['strike'] * 100
            poc = df_target.loc[df_target['notional_vol'].idxmax()]
            summary_stats['volume_poc_strike'] = float(poc['strike'])
            summary_stats['volume_poc_sent'] = 'C' if poc['callVolume'] > poc['putVolume'] else 'P'

        # [NEW] Spot GEX (Gamma at ATM Strike)
        try:
            # Find strike closest to spot price
            atm_row = df_target.iloc[(df_target['strike'] - spot_price).abs().argsort()[:1]]
            if not atm_row.empty:
                summary_stats['spot_gamma'] = float(atm_row['total_gamma_exp'].iloc[0])
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

        # Flip Point & Acceleration
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
                    
                    # [FIX] Calculate Acceleration (Distance to Flip)
                    # "Accel (R)" in UI -> How close are we to the flip?
                    # Let's map it to the flip price for now, or a delta metric.
                    # Actually, "Accel" usually implies rate of change.
                    # Simple heuristic: If Spot is within 1% of flip, Accel is HIGH.
                    # Or just return the Flip Price again? No, UI has Flip column.
                    # Let's return the GEX Notional of the Flip Strike itself as a proxy for "Force".
                    flip_row = df_sorted[df_sorted['strike'] == flip]
                    if not flip_row.empty:
                         # We'll use the Gamma Notional at the flip point as 'Accel'
                         # High Gamma at Flip = High Acceleration risk.
                         summary_stats['gex_velocity'] = float(flip_row['total_gamma_exp'].iloc[0])
                    break
        
        # Fallback: If no flip found or Velocity missing, use ratio
        if 'gex_velocity' not in summary_stats and summary_stats.get('total_gamma', 0) != 0:
             # Proxy: Total Gamma / 1 Billion (Normalized Force)
             summary_stats['gex_velocity'] = summary_stats['total_gamma'] / 1e9

        # Max Pain
        strikes_u = df_target['strike'].unique()
        if len(strikes_u) > 0:
            total_values = []
            sample = [s for s in strikes_u if s % 5 == 0]
            for px in sample:
                val = ((px - df_target['strike']).clip(lower=0) * df_target['callOpenInterest']).sum() + ((df_target['strike'] - px).clip(lower=0) * df_target['putOpenInterest']).sum()
                total_values.append((px, val))
            if total_values: summary_stats['max_pain_strike'] = float(min(total_values, key=lambda x: x[1])[0])

        return summary_stats
    except Exception as e:
        log(f"Calc Error: {e}")
        return summary_stats

def run_worker():
    log("GEX Worker Started.")
    while True:
        try:
            # 1. Get Spot Price
            spot = 0
            try:
                r = requests.get("https://api.orats.io/datav2/live/summaries", params={'token': ORATS_API_KEY, 'ticker': "SPY"}, timeout=10)
                if r.status_code == 200:
                    d = r.json().get('data', [{}])[0]
                    spy = float(d.get('stockPrice') or 0)
                    if spy > 0: spot = spy * 10
            except Exception as e: log(f"Spot Check Failed: {e}")

            if spot == 0:
                log("Zero Spot Price. Waiting...")
                time.sleep(60)
                continue

            # 2. Get GEX Data
            log("Fetching Options Chain...")
            master_orats = []
            # Try Live
            try:
                r = requests.get("https://api.orats.io/datav2/live/strikes", params={'token': ORATS_API_KEY, 'ticker': "SPX"}, timeout=45)
                if r.status_code == 200: master_orats = r.json().get('data', [])
            except: pass
            
            # Fallback Delayed
            if not master_orats:
                try:
                    r = requests.get("https://api.orats.io/datav2/strikes", params={'token': ORATS_API_KEY, 'ticker': "SPX"}, timeout=45)
                    if r.status_code == 200: master_orats = r.json().get('data', [])
                except: pass

            if not master_orats:
                log("No Options Data. Retrying in 1 min.")
                time.sleep(60)
                continue

            # 3. Analyze
            log(f"Analyzing {len(master_orats)} contracts at Spot ${spot:.2f}...")
            dates = get_next_n_trading_dates(get_trading_date(), 14)
            summaries = []
            
            for d in dates:
                d_str = d.strftime('%Y-%m-%d')
                stats = analyze_gamma_exposure(master_orats, spot, d_str)
                # Keep dict clean
                clean_stats = {k: (v if v is not None else 0) for k,v in stats.items()}
                clean_stats['date'] = d_str
                summaries.append(clean_stats)

            # 4. Save
            snapshot = {
                "timestamp": datetime.datetime.now().isoformat(),
                "spot": spot,
                "gex_profiles": summaries
            }
            
            with open(SNAPSHOT_FILE, 'w') as f:
                json.dump(snapshot, f, indent=4)
            log(f"Snapshot Saved to {SNAPSHOT_FILE}")

            # [NEW] Save Raw Chain for Wall Context (Source of Truth for OI/Delta)
            if master_orats:
                chain_file = "nexus_gex_chain.json"
                # Filter to save space
                slim_chain = []
                for c in master_orats:
                    try:
                        slim_chain.append({
                            "strike": float(c.get('strike', 0)),
                            "expiry": c.get('expirDate'),
                            "call_oi": int(float(c.get('callOpenInterest', 0))),
                            "put_oi": int(float(c.get('putOpenInterest', 0))),
                            "delta": float(c.get('delta', 0)), # Note: ORATS delta might be per-leg, check simple
                            "gamma": float(c.get('gamma', 0))
                        })
                    except: pass
                
                with open(chain_file, 'w') as f:
                    json.dump(slim_chain, f)
                log(f"Raw Chain Saved to {chain_file} ({len(slim_chain)} contracts)")

            # 5. Update Market Levels for Google Sheets (Bridge)
            # Find closest valid expiration (e.g. 0DTE/1DTE)
            if summaries:
                valid = next((s for s in summaries if s.get('short_gamma_wall_below') > 2000), summaries[0])
                levels = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "spx_price": spot,
                    "spy_price": spot/10,
                    "put_wall": (valid.get('short_gamma_wall_below',0)/10),
                    "call_wall": (valid.get('short_gamma_wall_above',0)/10),
                    "vol_trigger": (valid.get('volume_poc_strike',0)/10),
                    "spx_put_wall": valid.get('short_gamma_wall_below',0),
                    "spx_call_wall": valid.get('short_gamma_wall_above',0)
                }
                with open(MARKET_LEVELS_FILE, 'w') as f:
                    json.dump(levels, f, indent=4)
                log("Market Levels Updated.")

            # 6. Generate Wall Context (Delta Premium)
            # We need the full chain to calculate delta at specific strikes
            if master_orats:
                try:
                    # Load Levels to get walls
                    spx_call_wall = levels.get("spx_call_wall", 0)
                    spx_put_wall = levels.get("spx_put_wall", 0)
                    
                    wall_ctx = {"SPX": {}}
                    
                    # Helper to calc delta
                    def get_strike_delta(target_strike):
                        net_delta = 0
                        for c in master_orats:
                            try:
                                s = float(c.get('strike', 0))
                                if abs(s - target_strike) < 0.1:
                                    # Dealer Assumption: Dealers are Short Calls, Long Puts (Counter-party to Customer)
                                    # Actually, GEX models typically assume Dealers are SHORT OI.
                                    # Dealer Call Delta = -1 * Call_OI * Delta
                                    # Dealer Put Delta = -1 * Put_OI * Delta (Put Delta is negative, so this adds positive delta)
                                    
                                    c_oi = float(c.get('callOpenInterest', 0))
                                    p_oi = float(c.get('putOpenInterest', 0))
                                    # ORATS Delta is usually positive for Calls, Missing/Neg for Puts? 
                                    # We will trust the 'delta' field if provided, else estim.
                                    # However, ORATS 'delta' is usually per contract.
                                    
                                    # Robust Delta fetch
                                    c_delta = float(c.get('callDelta', 0.5)) # Fallback?
                                    if 'callDelta' not in c: c_delta = float(c.get('delta', 0.5)) # Sometime mixed
                                    
                                    p_delta = float(c.get('putDelta', -0.5))
                                    
                                    # Dealer Net Delta Notional = (Dealer Call Delta + Dealer Put Delta) * Spot * 100
                                    # Dealer Call Delta = -1 * c_oi * c_delta
                                    # Dealer Put Delta = -1 * p_oi * p_delta
                                    
                                    d_call = -1 * c_oi * c_delta
                                    d_put = -1 * p_oi * p_delta
                                    
                                    net_delta += (d_call + d_put)
                            except: pass
                        return net_delta * spot * 100


                    # [FIX] Broaden Context: Calculate Delta for ALL relevant strikes
                    # This prevents "Missing Premium" if Profile/Bridge picks a different wall than GEX Worker
                    target_strikes = sorted(list(set([float(c.get('strike', 0)) for c in master_orats])))
                    
                    saved_count = 0
                    for stk in target_strikes:
                        # Filter to relevant range (Spot +/- 250)
                        if abs(stk - spot) > 300: continue
                        
                        d_val = get_strike_delta(stk)
                        
                        # Save both formats to ensure Bridge finds it
                        wall_ctx["SPX"][str(stk)] = {"delta": d_val}
                        if stk.is_integer():
                            wall_ctx["SPX"][str(int(stk))] = {"delta": d_val}
                        
                        saved_count += 1

                    with open("nexus_walls_context.json", "w") as f:
                        json.dump(wall_ctx, f, indent=4)
                    log(f"Wall Context Saved. Covered {saved_count} strikes (Range +/- 300).")

                except Exception as e:
                    log(f"Wall Context Error: {e}")

            log(f"Sleeping {POLL_INTERVAL}s...")
            time.sleep(POLL_INTERVAL)

        except Exception as e:
            log(f"Fatal Worker Loop Error: {e}")
            time.sleep(60)

if __name__ == "__main__":
    run_worker()
