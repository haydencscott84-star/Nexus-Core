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

def check_keys():
    print(f"--- CHECKING BALANCE KEYS ---")
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID)
    balances = ts.get_account_balances()
    if balances:
        b = balances[0]
        print("KEYS:", list(b.keys()))
        print("FULL OBJ:", json.dumps(b, indent=2))
    else:
        print("NO BALANCES RETURNED")

if __name__ == "__main__":
    check_keys()
