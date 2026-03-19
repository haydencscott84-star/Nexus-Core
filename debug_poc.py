from analyze_snapshots import load_unified_data, calculate_market_structure_metrics
import pandas as pd

df = load_unified_data(90)

print("\nDEBUG: df columns:")
print(list(df.columns))

spy_df = pd.DataFrame()
if 'ticker' in df.columns:
    spy_df = df[df['ticker'] == 'SPY'].copy()
if spy_df.empty and 'symbol' in df.columns:
    spy_df = df[df['symbol'] == 'SPY'].copy()

if not spy_df.empty:
    target_strike_col = 'strike' if 'strike' in spy_df.columns else ('stk' if 'stk' in spy_df.columns else 'norm_strike')
    target_vol_col = 'volume' if 'volume' in spy_df.columns else ('vol' if 'vol' in spy_df.columns else 'size')

    spy_df = spy_df[pd.to_numeric(spy_df[target_strike_col], errors='coerce').notnull()]
    spy_df['strike'] = pd.to_numeric(spy_df[target_strike_col])
    spy_df['vol'] = pd.to_numeric(spy_df[target_vol_col], errors='coerce').fillna(0)
    
    spot_price = 690.0 # Approx
    spy_df = spy_df[spy_df['strike'].between(spot_price * 0.75, spot_price * 1.25)]
    vol_profile = spy_df.groupby('strike')['vol'].sum()
    poc = vol_profile.idxmax() if not vol_profile.empty else 0
    print(f"DEBUG: Calculated POC: {poc}")
    
    print("\nTop 5 Volume Strikes:")
    print(vol_profile.sort_values(ascending=False).head(5))
else:
    print("DEBUG: spy_df empty")
