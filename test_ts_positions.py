import json
import sys
from tradestation_explorer import TradeStationManager
from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID

def test_api():
    try:
        ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
        r1 = ts._make_api_request(f"/brokerage/accounts/{TS_ACCOUNT_ID}/positions")
        print(f"Main Account ({TS_ACCOUNT_ID}) Raw Response:")
        print(json.dumps(r1, indent=2))
        
        r2 = ts._make_api_request(f"/brokerage/accounts/210VGM01/positions")
        print(f"Futures Account (210VGM01) Raw Response:")
        print(json.dumps(r2, indent=2))
    except Exception as e:
        print(f"Test Exception: {e}")

if __name__ == "__main__":
    test_api()
