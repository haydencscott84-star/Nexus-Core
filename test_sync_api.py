import asyncio
import sys
import os
import json

sys.path.append(os.getcwd())

try:
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID
    from tradestation_explorer import TradeStationManager
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

def test_sync_calls():
    print(f"--- TESTING SYNC CALLS FOR {YOUR_ACCOUNT_ID} ---")
    
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID)
    print("Token:", ts.access_token[:10] + "...")
    
    # Test 1: Balances
    print("Fetching Balances...")
    try:
        balances = ts.get_account_balances()
        print(f"Balances Count: {len(balances)}")
        if balances:
            print("First Balance Sample:", json.dumps(balances[0])[:100] + "...")
        else:
            print("Balances Empty!")
    except Exception as e:
        print(f"Balances Error: {e}")

    # Test 2: Positions
    print("Fetching Positions...")
    try:
        positions = ts.get_positions()
        print(f"Positions Count: {len(positions)}")
        if positions:
            print("First Position Sample:", json.dumps(positions[0])[:100] + "...")
        else:
            print("Positions Empty!")
    except Exception as e:
        print(f"Positions Error: {e}")

if __name__ == "__main__":
    test_sync_calls()
