
import pandas as pd
import sys
import time
from datetime import datetime

# Add local path
import os
sys.path.append(os.getcwd())

print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 Starting Standalone Greeks Test...")

try:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 📦 Importing enrich_with_greeks...")
    from enrich_with_greeks import enrich_traps_with_greeks
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Import Successful.")
except ImportError as e:
    print(f"❌ Import Failed: {e}")
    sys.exit(1)

# Create Dummy Data (Matches SPY Traps structure)
print(f"[{datetime.now().strftime('%H:%M:%S')}] 🔨 Creating Dummy Data (SPY 500 Call)...")
df = pd.DataFrame([{
    'ticker': 'SPY',
    'strike': 500.0,
    'expiry': (datetime.now().replace(year=datetime.now().year + 1)).strftime('%Y-%m-%d'), # Future date
    'type': 'CALL',
    'vol': 1000
}])

print(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Input DataFrame:")
print(df)

# Run Enrichment (Blocking)
print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚡ Calling enrich_traps_with_greeks (Timeout depends on requests)...")
start = time.time()

try:
    enriched = enrich_traps_with_greeks(df)
    elapsed = time.time() - start
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Enrichment Returned in {elapsed:.2f}s!")
    
    print("\n📊 ENRICHED RESULT:")
    print(enriched[['ticker', 'strike', 'gamma', 'vega', 'theta', 'delta']].to_string())
    
    if 'gamma' in enriched.columns and enriched['gamma'].iloc[0] != 0:
        print("\n✅ SUCCESS: Gamma is populated!")
    else:
        print("\n⚠️ WARNING: Gamma is 0.0 (API returned data but maybe 0s?)")
        
except Exception as e:
    print(f"\n❌ CRITICAL FAILURE: {e}")
    import traceback
    traceback.print_exc()

print(f"[{datetime.now().strftime('%H:%M:%S')}] 🏁 Test Complete.")
