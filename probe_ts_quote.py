
import requests, os, json
from tradestation_explorer import TradeStationManager
from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID

# HEADLESS MODE IF NEEDED
TS = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
token = TS._get_valid_access_token()

url = f"{TS.BASE_URL}/marketdata/quotes/SPY"
headers = {"Authorization": f"Bearer {token}"}

print(f"Fetching Quote for SPY...")
r = requests.get(url, headers=headers)
if r.status_code == 200:
    data = r.json()
    if "Quotes" in data and data["Quotes"]:
        q = data["Quotes"][0]
        print("KEYS FOUND:")
        for k, v in q.items():
            print(f"{k}: {v}")
    else:
        print("No quotes in response.")
else:
    print(f"Error: {r.status_code} {r.text}")
