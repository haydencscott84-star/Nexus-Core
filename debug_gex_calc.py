import os
import asyncio
import aiohttp
import pandas as pd
import numpy as np
import datetime

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TARGET_DATE = "2026-01-30"

def analyze_gamma_exposure(strikes_data, spot_price, target_date_str):
    print(f"\n--- ANALYZING {target_date_str} (Spot: {spot_price}) ---")
    summary_stats = {
        'total_gamma': 0, 'spot_gamma': 0, 'max_pain_strike': None, 'volume_poc_strike': None,
        'volume_poc_sent': 'N/A', 'short_gamma_wall_above': None, 'short_gamma_wall_below': None,
        'long_gamma_wall_above': None, 'long_gamma_wall_below': None,
        'pc_ratio_volume': None, 'pc_ratio_oi': None, 'gex_flip_point': None
    }
    
    df = pd.DataFrame(strikes_data)
    df['expirDate_dt'] = pd.to_datetime(df['expirDate']).dt.date
    target_dt = pd.to_datetime(target_date_str).date()
    df_target = df[df['expirDate_dt'] == target_dt].copy()
    
    if df_target.empty:
        print("DF Target Empty!")
        return summary_stats

    cols = ['gamma', 'callOpenInterest', 'putOpenInterest', 'callVolume', 'putVolume', 'strike']
    for c in cols: df_target[c] = pd.to_numeric(df_target[c], errors='coerce').fillna(0)
    
    call_gex = df_target['callOpenInterest'] * 100 * df_target['gamma']
    put_gex = (df_target['putOpenInterest'] * 100 * df_target['gamma'])
    total_gex_units = (call_gex - put_gex) 
    
    df_target['total_gamma_exp'] = total_gex_units.sum() * (spot_price**2) * 0.01
    df_target['total_gamma_exp'] = total_gex_units * (spot_price**2) * 0.01
    
    # Check Walls
    sig_gex = df_target[df_target['total_gamma_exp'].abs() > 1.0].copy()
    print(f"Significant GEX Strikes (>1.0): {len(sig_gex)}")
    
    if not sig_gex.empty:
        short_gex = sig_gex[sig_gex['total_gamma_exp'] < 0]
        long_gex = sig_gex[sig_gex['total_gamma_exp'] > 0]
        print(f"Short GEX Rows: {len(short_gex)}")
        print(f"Long GEX Rows: {len(long_gex)}")
        
        if not long_gex.empty:
            below = long_gex[long_gex['strike'] < spot_price]
            print(f"Long GEX Below Spot ({spot_price}): \n{below[['strike', 'total_gamma_exp']]}")
            if not below.empty:
                row = below.loc[below['total_gamma_exp'].idxmax()]
                print(f"Found Pin (S): {row['strike']}")
            else:
                print("No Long GEX below spot.")
    
    # Check Flip
    df_sorted = df_target.sort_values('strike')
    strikes = df_sorted['strike'].values
    gammas = df_sorted['total_gamma_exp'].values
    
    found_flip = False
    for i in range(len(strikes) - 1):
        g1 = gammas[i]; g2 = gammas[i+1]
        if (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
            if abs(g1) < abs(g2): flip = strikes[i]
            else: flip = strikes[i+1]
            
            dist = abs(flip - spot_price)
            limit = spot_price * 0.05
            print(f"Potential Flip at {flip}. Dist: {dist:.2f} (Limit: {limit:.2f})")
            
            if dist < limit:
                print(f"VALID FLIP: {flip}")
                found_flip = True
                break
    
    if not found_flip: print("No Valid Flip Found.")
    return summary_stats

async def main():
    async with aiohttp.ClientSession() as session:
        print("Fetching Live Price...")
        spot = 687.0 # Default fallback
        try:
            async with session.get("https://api.orats.io/datav2/live/summaries", params={'token': ORATS_API_KEY, 'ticker': "SPY"}, timeout=10) as r:
                d = (await r.json()).get('data', [{}])[0]
                spot = float(d.get('stockPrice'))
                print(f"Live SPY: {spot}")
        except Exception as e:
            print(f"Price Fetch Err: {e}")

        print("Fetching Strikes...")
        async with session.get("https://api.orats.io/datav2/live/strikes", params={'token': ORATS_API_KEY, 'ticker': 'SPY'}, timeout=45) as r:
            data = await r.json()
            rows = data.get('data', [])
            print(f"Loaded {len(rows)} strikes.")
            
            analyze_gamma_exposure(rows, spot, TARGET_DATE)

if __name__ == "__main__":
    asyncio.run(main())
