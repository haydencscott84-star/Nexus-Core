import pandas as pd
from analyze_snapshots import load_unified_data

df = load_unified_data(5)
spy_df = df[df['ticker'] == 'SPY'].copy()
if 'date' in spy_df.columns and not spy_df.empty:
    latest_date = spy_df['date'].max()
    spy_df = spy_df[spy_df['date'] == latest_date]
    print(f"Initial row count: {len(spy_df)}")
    
    now_ts = pd.Timestamp.now().normalize()
    print(f"Now TS: {now_ts}")
    if 'expiry' in spy_df.columns:
        spy_df['expiry_dt'] = pd.to_datetime(spy_df['expiry'], errors='coerce')
        mask_nat = spy_df['expiry_dt'].isna()
        print(f"Missing Expiry DT: {mask_nat.sum()}")
        
        if mask_nat.any() and 'date' in spy_df.columns and 'dte' in spy_df.columns:
            spy_df['date_ts'] = pd.to_datetime(spy_df['date'])
            spy_df.loc[mask_nat, 'expiry_dt'] = spy_df.loc[mask_nat, 'date_ts'] + pd.to_timedelta(spy_df.loc[mask_nat, 'dte'], unit='D')
            
        print(f"Min Expiry DT: {spy_df['expiry_dt'].min()}, Max Expiry DT: {spy_df['expiry_dt'].max()}")
        spy_df = spy_df[spy_df['expiry_dt'] >= now_ts]
        print(f"Row count after expiry filter: {len(spy_df)}")
        print(f"Gamma sum: {spy_df['gamma'].sum()}")
