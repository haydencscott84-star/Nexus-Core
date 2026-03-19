import pandas as pd
import analyze_snapshots
from analyze_snapshots import load_unified_data, calculate_market_structure_metrics

# Load Data (Today)
print("LOADING DATA...")
# df = load_unified_data(0)
# Mocking cleanup logic from load_unified_data
try:
    df = pd.read_csv("spy_debug.csv")
    print(f"LOADED: {len(df)} rows")
    
    # Standardize Cols (Mini version of load_unified_data)
    if 'stk' in df.columns: df['strike'] = pd.to_numeric(df['stk'], errors='coerce')
    if 'exp' in df.columns: df['expiry'] = df['exp']
    if 'vol' in df.columns: df['vol'] = pd.to_numeric(df['vol'], errors='coerce').fillna(0)
    if 'gamma' in df.columns: df['gamma'] = pd.to_numeric(df['gamma'], errors='coerce').fillna(0)
    if 'symbol' in df.columns: df['ticker'] = df['symbol']
    # Auto-correct ticker logic
    def auto_correct_ticker(row):
        if row['strike'] > 2000: return "SPX"
        if row['strike'] < 1500: return "SPY"
        return row['ticker']
    df['ticker'] = df.apply(auto_correct_ticker, axis=1)

except Exception as e:
    print(f"LOAD ERROR: {e}")
    df = pd.DataFrame()

# Run Logic
spot = 685.0 # Approx
metrics = calculate_market_structure_metrics(df, spot)

print("\n--- RESULTS ---")
print(f"FLOW PAIN: {metrics['flow_pain']}")
print(f"TOP GEX:\n{metrics['top_gex']}")
print(f"DETAILS: {metrics['top_gex_details']}")

# Check if 1000 is in there
if not metrics['top_gex'].empty:
    biggest = metrics['top_gex'].abs().idxmax()
    print(f"\nMAGNET: {biggest}")
    
# Check for strikes around 1000 in source
if not df.empty:
    spy_df = df[df['ticker'] == 'SPY']
    print(f"\nSPY Strikes near 1000:")
    print(spy_df[(spy_df['strike'] >= 990) & (spy_df['strike'] <= 1010)][['strike', 'ticker', 'vol', 'gamma']])
