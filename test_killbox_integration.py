
import pandas as pd
import sys
import os
from datetime import datetime, timedelta

# Add local path
sys.path.append(os.getcwd())

print("🚀 STARTING INTEGRATION TEST Check...")

try:
    from enrich_with_greeks import enrich_traps_with_greeks
except ImportError:
    print("❌ Failed to import enrichor")
    sys.exit(1)

# 1. SETUP DUMMY DATA
print("🔨 Building Dummy Data...")

# [FIX] Fetch a REAL active expiration from ORATS first
from orats_connector import get_live_chain
try:
    print("📡 Fetching live chain to get valid expiry...")
    live_chain = get_live_chain("SPY")
    if live_chain.empty:
        print("❌ Could not fetch live chain. Using fallback.")
        expiry = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
    else:
        # Pick the most common expiry
        valid_expiries = live_chain['expirDate'].unique()
        expiry = valid_expiries[0] # Pick first valid one
        print(f"✅ Using Real Expiry: {expiry}")
except:
    expiry = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')


# Mock 'active_df' (Source Data)
data = []

if 'live_chain' in locals() and not live_chain.empty:
    # Use REAL data from the chain we just fetched to guarantee matches
    sample = live_chain.head(20)
    print(f"✅ Using {len(sample)} Real Rows for Input Generation")
    print(f"DEBUG: Live Chain Columns: {live_chain.columns.tolist()}")
    print(f"DEBUG: First Row Keys: {sample.iloc[0].keys()}")
    for _, row in sample.iterrows():
        # Fallback for ticker if missing
        ticker_val = row.get('ticker') or row.get('symbol') or "SPY"
        strike_val = row.get('strike')
        expiry_val = row.get('expiry') # Connector renames 'expirDate' to 'expiry'
        
        data.append({
            'ticker': ticker_val,
            'strike': strike_val,
            'expiry': expiry_val,
            'type': 'CALL', # ORATS 'delta' implies call usually, checking logic
            'vol': 100,
            'premium': 5.0,
            'oi': 500,
            'delta': 0.5,
            'breakeven': row['strike'] + 5.0
        })
else:
    # Fallback (Should not happen if API works)
    for i in range(20):
        data.append({
            'ticker': 'SPY',
            'strike': 500 + i,
            'expiry': expiry,
            'type': 'CALL',
            'vol': 100,
            'premium': 5.0,
            'oi': 500,
            'delta': 0.5,
            'breakeven': 505.0
        })

active_df = pd.DataFrame(data)

# 2. MIMIC build_kill_box LOGIC (Lines ~880-910 in analyze_snapshots.py)
SPY_PRICE = 450.0
SPX_PRICE = 4500.0

# Calls
calls = active_df[active_df['type'] == 'CALL'].copy()
calls['avg_prem'] = 1.0 # Mock
calls['status'] = "TRAPPED BULLS"

# Puts - Aggregation Logic
puts_raw = active_df[active_df['type'] == 'PUT']
puts = puts_raw.groupby(['ticker', 'strike', 'expiry']).agg({
    'premium': 'sum', 'vol': 'sum', 'oi': 'max', 'delta': 'mean'
}).reset_index()
puts['oi_delta'] = puts['oi'] * puts['delta'] * 100.0
puts['avg_prem'] = puts['premium'] / puts['vol']
puts['breakeven'] = puts['strike'] - (puts['avg_prem'] / 100.0)
puts['type'] = 'PUT'
puts['status'] = "TRAPPED BEARS"

# Merge
merged = pd.concat([calls, puts], ignore_index=True)
trapped = merged.copy()
trapped['abs_exposure'] = 1000.0 

# Sort & Slice
spy_traps = trapped[trapped['ticker'] == 'SPY'].head(20)

print(f"📊 Validating SPY Traps Input ({len(spy_traps)} rows):")
print(spy_traps[['ticker', 'strike', 'type', 'expiry']].head())
print("-" * 30)

# 3. RUN ENRICHMENT
print("⚡ Enriching with Greeks (Local Call)...")
try:
    enriched = enrich_traps_with_greeks(spy_traps)
    
    print("\n✅ Enrichment Finished.")
    print(enriched[['ticker', 'strike', 'type', 'gamma', 'vega']].head(10).to_string())
    
    # Validation
    gamma_sum = enriched['gamma'].sum()
    print(f"\n🔢 Total Gamma: {gamma_sum}")
    
    if gamma_sum == 0 and len(enriched) > 0:
        print("❌ FAILURE: Gamma is all 0.0!")
    else:
        print("✅ SUCCESS: Data populated.")
        
except Exception as e:
    print(f"❌ CRASH: {e}")
    import traceback
    traceback.print_exc()
