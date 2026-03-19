
import sys
import os
import pandas as pd
import asyncio

# Add script dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from orats_connector import get_live_chain
except ImportError:
    print("CRITICAL: orats_connector.py not found or failed to import.")
    sys.exit(1)

def analyze_spx_greeks():
    print("--- STARTING SPX GREEKS DEBUG ---")
    print("Fetching live chain for SPX...")
    
    try:
        df = get_live_chain("SPX")
    except Exception as e:
        print(f"CRITICAL: API Fetch Failed: {e}")
        return

    if df.empty:
        print("RESULT: No data returned from API (Empty DataFrame).")
        return

    print(f"RESULT: API returned {len(df)} rows.")
    
    # Check Greek Columns
    greek_cols = ['delta', 'gamma', 'vega', 'theta']
    missing_cols = [c for c in greek_cols if c not in df.columns]
    
    if missing_cols:
        print(f"WARNING: Missing Greek Columns: {missing_cols}")
        print(f"Available Columns: {df.columns.tolist()}")
    else:
        print("SUCCESS: All Greek columns present.")

    # Check for Non-Zero Values
    for col in greek_cols:
        if col in df.columns:
            # Force numeric
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
            
            non_zeros = df[df[col].abs() > 0.0001]
            count = len(non_zeros)
            
            print(f"COLUMN '{col}': {count} non-zero rows out of {len(df)}.")
            if count > 0:
                print(f"   Sample: {non_zeros[col].head(3).tolist()}")
            else:
                print(f"   ⚠️  ALL VALUES ARE ZERO.")

    print("--- DEBUG COMPLETE ---")

if __name__ == "__main__":
    analyze_spx_greeks()
