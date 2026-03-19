import requests
import json
import os
import sys

# Load Config
try:
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
    from tradestation_explorer import TradeStationManager
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

# Initialize TS
ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
token = ts._get_valid_access_token()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
url = f"{ts.BASE_URL}/orderexecution/orders"

# Test 1: The Failing Payload (Buy/Sell)
print("\n--- TEST 1: Generic Buy/Sell (Current Code) ---")
payload_fail = {
    "AccountID": TS_ACCOUNT_ID,
    "OrderType": "Limit",
    "LimitPrice": "0.01", # Safety
    "TimeInForce": {"Duration": "Day"},
    "Route": "Intelligent",
    "Legs": [
        {"Symbol": "SPY 260130P600", "Quantity": "1", "TradeAction": "Buy", "AssetType": "Option"},
        {"Symbol": "SPY 260130P605", "Quantity": "1", "TradeAction": "Sell", "AssetType": "Option"}
    ]
}
r1 = requests.post(url, json=payload_fail, headers=headers)
print(f"Status: {r1.status_code}")
print(f"Response: {r1.text}")

# Test 2: The Proposed Fix (BuyToOpen/SellToOpen)
print("\n--- TEST 2: BuyToOpen/SellToOpen (Proposed Fix) ---")
payload_fix = {
    "AccountID": TS_ACCOUNT_ID,
    "OrderType": "Limit",
    "LimitPrice": "0.01", # Safety
    "TimeInForce": {"Duration": "Day"},
    "Route": "Intelligent",
    "Legs": [
        {"Symbol": "SPY 260130P600", "Quantity": "1", "TradeAction": "BuyToOpen", "AssetType": "Option"},
        {"Symbol": "SPY 260130P605", "Quantity": "1", "TradeAction": "SellToOpen", "AssetType": "Option"}
    ]
}
r2 = requests.post(url, json=payload_fix, headers=headers)
print(f"Status: {r2.status_code}")
print(f"Response: {r2.text}")
