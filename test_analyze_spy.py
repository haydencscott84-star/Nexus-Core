import pandas as pd
import glob
import os
import analyze_snapshots as ana
import warnings
warnings.filterwarnings('ignore')

# We can mimic Phase 1 refresh logic
ana.DATA_SOURCES = {
    'spy': 'snapshots_spy',       
    'spx': 'snapshots'            
}

df = ana.load_unified_data(0, log_func=print)
print(f"Total rows loaded: {len(df)}")

spy_df = df[df['ticker'] == 'SPY']
print(f"Total SPY rows: {len(spy_df)}")

# Check SPY_PRICE
live_spy = 0.0
derived_spot = 0.0
spy_rows = df[(df['ticker'] == 'SPY') & (df['underlying_price'] > 610.0)]
if not spy_rows.empty:
    derived_spot = float(spy_rows['underlying_price'].iloc[-1])

SPY_PRICE = derived_spot
if SPY_PRICE == 0: SPY_PRICE = 685.0

print(f"SPY_PRICE: {SPY_PRICE}")

# Let's inspect the first row of SPY data to see columns and strike format
if not spy_df.empty:
    print(spy_df.iloc[-1])

# Run build kill box logic up to filtering
today_ts = pd.Timestamp(ana.get_today_date())
df['expiry_dt'] = pd.to_datetime(df['expiry'], errors='coerce')
mask_nat = df['expiry_dt'].isna()
if mask_nat.any():
    df['date'] = pd.to_datetime(df['date'])
    df.loc[mask_nat, 'expiry_dt'] = df.loc[mask_nat, 'date'] + pd.to_timedelta(df.loc[mask_nat, 'dte'], unit='D')

active_df = df[df['expiry_dt'] >= today_ts].copy()

# Filter Extreme OTM
eff_spx = (SPY_PRICE * 10.03)
eff_spy = SPY_PRICE

cond_spx = (active_df['ticker'] == 'SPX') & (active_df['strike'].between(eff_spx * 0.95, eff_spx * 1.05))
cond_spy = (active_df['ticker'] == 'SPY') & (active_df['strike'].between(eff_spy * 0.95, eff_spy * 1.05))

merged_initial = active_df[cond_spx | cond_spy].copy() 
print(f"Merged Initial len: {len(merged_initial)}")
spy_active = merged_initial[merged_initial['ticker'] == 'SPY']
print(f"SPY Active len: {len(spy_active)}")

# Process Calls
calls = spy_active[spy_active['type'] == 'CALL']
print(f"SPY Active Calls: {len(calls)}")
if len(calls) > 0:
    g_calls = calls.groupby(['ticker', 'strike', 'expiry', 'dte']).agg({
        'premium': 'sum', 'vol': 'sum', 'oi': 'max', 'delta': 'mean', 'gamma': 'mean', 'vega': 'mean', 'theta': 'mean'
    }).reset_index()
    print(f"Grouped Calls: {len(g_calls)}")
