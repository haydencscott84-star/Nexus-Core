import pandas as pd
from enrich_with_greeks import enrich_traps_with_greeks
import logging

# Configure Logging to match what the user will see in TUI/Log
logging.basicConfig(level=logging.INFO)

def test_merge_logic():
    print("\n--- TEST: Greeks Enrichment Logic ---")
    
    # 1. Simulate Local Snapshots (Trap DB)
    # Varied formats: integer strike vs float, string expiry
    traps_data = [
        {'ticker': 'SPY', 'strike': 710, 'expiry': '2025-12-20', 'type': 'CALL', 'vol': 100},      # Int strike
        {'ticker': 'SPY', 'strike': 715.0, 'expiry': '2025-12-20', 'type': 'PUT', 'vol': 200},     # Float strike
        {'ticker': 'SPY', 'strike': 680, 'expiry': '2025-12-20', 'type': 'PUT', 'vol': 500},       # Int strike
        {'ticker': 'SPY', 'strike': 681.5, 'expiry': '2025-12-20', 'type': 'CALL', 'vol': 50}      # Decimal strike
    ]
    traps_df = pd.DataFrame(traps_data)
    print(f"Local Data:\n{traps_df}")

    # 2. Mock 'get_live_chain' from ORATS
    # ORATS returns floats for strikes, YYYY-MM-DD for expiry
    # We will mock the function by Monkey Patching locally for this test
    import enrich_with_greeks
    
    def mock_get_live_chain(ticker):
        print(f"DEBUG: Mock Fetching for {ticker}")
        mock_rows = [
            # Exact matches (but raw format)
            {'ticker': 'SPY', 'strike': 710.0, 'expirDate': '2025-12-20', 'type': 'CALL', 'delta': 0.5, 'gamma': 0.05, 'theta': -0.1, 'vega': 0.2},
            {'ticker': 'SPY', 'strike': 715.0, 'expirDate': '2025-12-20', 'type': 'PUT', 'delta': -0.4, 'gamma': 0.04, 'theta': -0.09, 'vega': 0.18},
            {'ticker': 'SPY', 'strike': 680.0001, 'expirDate': '2025-12-20', 'type': 'PUT', 'delta': -0.6, 'gamma': 0.03, 'theta': -0.08, 'vega': 0.15}, # Slight precision diff
            {'ticker': 'SPY', 'strike': 681.5, 'expirDate': '2025-12-20', 'type': 'CALL', 'delta': 0.9, 'gamma': 0.01, 'theta': -0.2, 'vega': 0.1},
        ]
        # In real ORATS connector, we transform this before returning DataFrame
        # But 'orats_connector.py' does the transformation.
        # So we should simulate what 'orats_connector.get_live_chain' returns.
        # It returns DF with cols: strike, type, expiry, delta...
        
        df = pd.DataFrame(mock_rows)
        # Rename to match connector output
        df.rename(columns={'expirDate': 'expiry'}, inplace=True)
        return df

    enrich_with_greeks.get_live_chain = mock_get_live_chain
    
    # 3. Run Enrichment
    result = enrich_with_greeks.enrich_traps_with_greeks(traps_df)
    
    # 4. Verify
    print("\n--- Result Dataframe ---")
    print(result[['ticker', 'strike', 'expiry', 'type', 'delta', 'gamma']])
    
    print("\n--- Validation ---")
    zeros = result[result['gamma'] == 0]
    if not zeros.empty:
        print(f"❌ FAILED: {len(zeros)} rows have 0 Gamma (Merge Failed)")
        print(zeros)
    else:
        print("✅ SUCCESS: All rows merged and have Greek values.")

if __name__ == "__main__":
    test_merge_logic()
