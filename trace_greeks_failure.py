
import sys
import os
import pandas as pd
import json

# Add current dir to path
sys.path.append(os.getcwd())

from orats_connector import get_live_chain
from enrich_with_greeks import enrich_traps_with_greeks

def test_orats_direct():
    print("--- TESTING ORATS DIRECT FETCH ---")
    tickers = ["SPY", "SPXW", "SPX"]
    
    for t in tickers:
        print(f"\nFetching {t}...")
        df = get_live_chain(t)
        
        if df.empty:
            print(f"❌ {t}: Returned EMPTY DataFrame.")
            continue
            
        print(f"✅ {t}: Returned {len(df)} rows.")
        
        # Analyze Greeks
        if 'delta' in df.columns:
            non_zero_delta = df[df['delta'] != 0].shape[0]
            print(f"   Non-Zero Delta: {non_zero_delta} / {len(df)}")
            
            # Sample
            sample = df[df['delta'] != 0].head(1)
            if not sample.empty:
                print(f"   Valid Sample: {sample[['expiry', 'strike', 'type', 'delta', 'gamma']].to_dict(orient='records')}")
            else:
                print(f"   ⚠️ ALL DELTAS ARE ZERO. Dumping raw sample:")
                print(df[['expiry', 'strike', 'type', 'delta']].head(3))
        else:
            print("   ❌ Column 'delta' MISSING.")

def test_enrichment_logic():
    print("\n--- TESTING ENRICHMENT LOGIC ---")
    # Create a dummy trap DF that should match real data
    # We need a date that is likely to exist. 
    # Let's verify what dates exist from the direct fetch first.
    
    # We'll use SPY for this test as it's most reliable
    print("Fetching SPY for Enrichment Test base...")
    real_chain = get_live_chain("SPY")
    if real_chain.empty:
        print("Skipping Enrichment Test (No SPY Data)")
        return

    # Pick a random row to simulate a "Trap"
    target_row = real_chain.iloc[0]
    
    traps_df = pd.DataFrame([{
        'ticker': 'SPY',
        'strike': target_row['strike'],
        'expiry': target_row['expiry'], # Should match format
        'type': target_row['type']
    }])
    
    print(f"Simulating Trap: {traps_df.to_dict(orient='records')}")
    
    enriched = enrich_traps_with_greeks(traps_df)
    
    print("Enriched Result:")
    print(enriched.to_dict(orient='records'))
    
    if enriched.iloc[0]['delta'] != 0:
        print("✅ SUCCESS: Enrichment populated Delta.")
    else:
        print("❌ FAILURE: Enrichment failed (Delta is 0).")

if __name__ == "__main__":
    test_orats_direct()
    # test_enrichment_logic()
