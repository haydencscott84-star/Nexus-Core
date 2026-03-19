from api_manager import API_MANAGER

print("Testing API Manager Integration...")

# Test TS Fetch
print("\n[1] Fetching SPY Chain from TradeStation (Priority 1)...")
chain_ts = API_MANAGER.fetch_chain("SPY", source="TRADESTATION")
if chain_ts:
    print(f"SUCCESS: Fetched {len(chain_ts)} rows from TradeStation.")
    print("Sample:", chain_ts[0] if len(chain_ts) > 0 else "Empty")
else:
    print("FAILURE: No data from TradeStation (or empty chain).")

# Test ORATS Fetch (Optional, just to verify routing)
print("\n[2] Fetching SPY Chain from ORATS (Priority 2)...")
chain_orats = API_MANAGER.fetch_chain("SPY", source="ORATS")
if not chain_orats.empty:
    print(f"SUCCESS: Fetched {len(chain_orats)} rows from ORATS.")
else:
    print("FAILURE: No data from ORATS.")
