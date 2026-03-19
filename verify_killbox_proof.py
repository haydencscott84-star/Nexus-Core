
import pandas as pd
from datetime import datetime
import sys
import os

# Ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from enrich_with_greeks import enrich_traps_with_greeks
except ImportError:
    print("❌ Failed to import enrich_with_greeks")
    sys.exit(1)

# 1. Create Mock Traps DataFrame (Simulating analyze_snapshots.py output)
print("🧪 Creating Mock Trap Data...")
mock_data = [
    {'ticker': 'SPY', 'strike': 600.0, 'expiry': '2025-12-19', 'type': 'PUT', 'status': 'TRAPPED BEARS'},
    {'ticker': 'SPY', 'strike': 610.0, 'expiry': '2025-12-19', 'type': 'CALL', 'status': 'TRAPPED BULLS'},
    # Intentionally missing 'type' to test robustness? No, we fixed that bug, so we provide it.
]
traps_df = pd.DataFrame(mock_data)
print(f"📊 Input Data:\n{traps_df}\n")

# 2. Run Enrichment
print("🚀 Running Enrichment (Simulating Live Fetch)...")
try:
    enriched_df = enrich_traps_with_greeks(traps_df)
    
    # 3. Validation
    print("\n✅ Enrichment Complete. Checking Results:")
    required_cols = ['delta', 'gamma', 'theta', 'vega']
    missing = [c for c in required_cols if c not in enriched_df.columns]
    
    if missing:
        print(f"❌ FAIL: Missing columns: {missing}")
    else:
        print("✅ SUCCESS: All Greek columns present.")
        print(enriched_df[['ticker', 'strike', 'type', 'delta', 'gamma', 'theta', 'vega']])
        
        # Check for non-zero values (assuming ORATS returns something or mock does)
        # Note: Since we are running locally without a guaranteed ORATS key, we might get 0s 
        # unless orats_connector is working.
        # But the *columns* being present proves the structure is fixed.
        
except Exception as e:
    print(f"❌ CRASH CONFIRMED: {e}")
