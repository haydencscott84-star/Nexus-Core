import requests
import pandas as pd
import numpy as np
import os
import datetime
from datetime import timedelta

# CONFIG
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"

def get_orats_data_sync(endpoint_type):
    api_url = f"https://api.orats.io/datav2/live/{endpoint_type}"
    params = {'token': ORATS_API_KEY.strip(), 'ticker': TICKER}
    try:
        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        result_data = data.get('data', data)
        return result_data
    except Exception as e:
        print(f"Error fetching {endpoint_type}: {e}")
        return None

def analyze_flip(strikes_data, spy_price, target_date):
    print(f"\n--- ANALYZING {target_date} (Spot: {spy_price}) ---")
    
    if not strikes_data:
        print("No strikes data.")
        return

    df = pd.DataFrame(strikes_data)
    # Check expiry
    df_target = df[df['expirDate'] == target_date].copy()
    if df_target.empty:
        print("No data for target date.")
        return

    # Convert cols
    required_cols = ['expirDate', 'strike', 'gamma', 'callOpenInterest', 'putOpenInterest']
    for col in required_cols[1:]:
             df_target[col] = pd.to_numeric(df_target[col], errors='coerce')
    df_target.fillna(0, inplace=True)
    df_target.sort_values('strike', inplace=True)

    # Calculate GEX
    call_gex = df_target['callOpenInterest'] * 100 * df_target['gamma']
    put_gex = (df_target['putOpenInterest'] * 100 * df_target['gamma'])
    total_gex = (call_gex - put_gex) 
    df_target['total_gamma_exp'] = total_gex * (spy_price**2) * 0.01

    # Print a window around spot
    near_spot = df_target[(df_target['strike'] > spy_price - 10) & (df_target['strike'] < spy_price + 10)]
    print("Strikes near spot:")
    print(near_spot[['strike', 'total_gamma_exp']])

    # FLIP LOGIC
    values = df_target[['strike', 'total_gamma_exp']].values
    strikes = values[:, 0]
    gammas = values[:, 1]

    best_flip = None
    flips_found = []
    
    for i in range(len(strikes) - 1):
        g1 = gammas[i]; g2 = gammas[i+1]
        if (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
            s1 = strikes[i]
            s2 = strikes[i+1]
            
            # Linear Interpolation for precise zero crossing?
            # The current logic just takes the smaller GEX strike.
            if abs(g1) < abs(g2): flip = s1
            else: flip = s2
            
            dist = abs(flip - spy_price)
            limit = spy_price * 0.05
            
            flips_found.append((flip, dist, limit, g1, g2))

            if dist < limit:
                if best_flip is None:
                    best_flip = float(flip)
                    # Note: original code breaks here.
                    # break 

    print("\nFlips Found (Strike, Distance, Limit, G1, G2):")
    for f in flips_found:
        status = "ACCEPTED" if f[0] == best_flip else ("VALID" if f[1] < f[2] else "TOO FAR")
        print(f"{f[0]} | Dist: {f[1]:.2f} (Limit {f[2]:.2f}) | {status}")

    print(f"\nResult Best Flip: {best_flip}")

# MAIN EXECUTION
print("Fetching Data...")
summary_data = get_orats_data_sync('summaries')
strikes_data = get_orats_data_sync('strikes')

if summary_data and strikes_data:
    d = summary_data[0] if isinstance(summary_data, list) else summary_data
    price = float(d.get('stockPrice') or d.get('last') or 0)
    print(f"Current SPY Price: {price}")
    
    # Get today's date string
    # Assuming the first date in strikes data is today/next expiry
    # But let's look for the one in the screenshot: 2026-01-27
    target_date = "2026-01-27"
    
    analyze_flip(strikes_data, price, target_date)
else:
    print("Failed to fetch data.")
