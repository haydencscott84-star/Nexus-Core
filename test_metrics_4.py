import pandas as pd
from analyze_snapshots import load_unified_data, calculate_market_structure_metrics

# Recreate the function but with prints
def calc_metrics_debug(df, spot_price):
    results = {'flow_pain': 0, 'top_gex': pd.Series(dtype=float), 'top_gex_details': []}
    spy_df = df[df['ticker'] == 'SPY'].copy()
    print(f"1. Init SPY: {len(spy_df)}")
    
    if 'date' in spy_df.columns and not spy_df.empty:
        latest_date = spy_df['date'].max()
        spy_df = spy_df[spy_df['date'] == latest_date]
        print(f"2. After date filter: {len(spy_df)}")

    try:
        now_ts = pd.Timestamp.now().normalize()
        if 'expiry' in spy_df.columns:
            spy_df['expiry_dt'] = pd.to_datetime(spy_df['expiry'], errors='coerce')
            mask_nat = spy_df['expiry_dt'].isna()
            if mask_nat.any() and 'date' in spy_df.columns and 'dte' in spy_df.columns:
                spy_df['date_ts'] = pd.to_datetime(spy_df['date'])
                spy_df.loc[mask_nat, 'expiry_dt'] = spy_df.loc[mask_nat, 'date_ts'] + pd.to_timedelta(spy_df.loc[mask_nat, 'dte'], unit='D')
            spy_df = spy_df[spy_df['expiry_dt'] >= now_ts]
            print(f"3. After Expiry Filter: {len(spy_df)}")
    except Exception as e:
        print(f"Expiry Filter Error: {e}")

    spot = spot_price
    print(f"Initial Spot: {spot}")
    if spot <= 0 and not spy_df.empty:
        if 'underlying_price' in spy_df.columns:
             valid_prices = spy_df[spy_df['underlying_price'] > 10.0]['underlying_price']
             if not valid_prices.empty: spot = valid_prices.iloc[-1]
    if spot <= 10: spot = 690.0
    print(f"Final Spot: {spot}")

    spy_df = spy_df[spy_df['strike'].between(spot * 0.75, spot * 1.25)]
    print(f"4. After Strike Range Filter: {len(spy_df)}")

    print(f"Gamma check - sum: {spy_df['gamma'].sum()}")
    if 'gamma' not in spy_df.columns or spy_df['gamma'].sum() == 0:
         print("Aborted at Gamma check")
         return results

    spy_df['flow_gex'] = spy_df['gamma'] * spy_df['vol'] * spot * 100
    gex_profile = spy_df.groupby('strike')['flow_gex'].sum().sort_index()
    print(f"GEX Profile generated with {len(gex_profile)} strikes")
    
    results['top_gex'] = gex_profile.abs().nlargest(3)
    print(f"Top GEX: {results['top_gex']}")
    return results

df = load_unified_data(5)
res = calc_metrics_debug(df, 670.0)
print(res['top_gex'])
