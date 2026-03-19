import os
import requests, json, os, sys
# Ensure script dir is in path
sys.path.append(os.getcwd())
from tradestation_explorer import TradeStationManager

# Config from nexus_config
try:
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except:
    TS_CLIENT_ID = os.environ.get("TS_CLIENT_ID", "YOUR_TS_CLIENT_ID")
    TS_CLIENT_SECRET = os.environ.get("TS_CLIENT_SECRET", "YOUR_TS_CLIENT_SECRET")
    TS_ACCOUNT_ID = os.environ.get("TS_ACCOUNT_ID", "YOUR_ACCOUNT_ID")

ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
access_token = ts._get_valid_access_token()
headers = {"Authorization": f"Bearer {access_token}"}
print("TOKEN REFRESHED.")

# 4. Check 'balances' for Futures
url = f"https://api.tradestation.com/v3/brokerage/accounts/210VGM01/balances"
print(f"--- FETCHING FUTURES BALANCE (210VGM01) ---")
try:
    r = requests.get(url, headers=headers, timeout=5)
    print(f"STATUS: {r.status_code}")
    print(r.text)
except Exception as e:
    print(f"ERR: {e}")
