import os
import requests, json, os

ACCOUNT_ID = os.environ.get("TS_ACCOUNT_ID", "YOUR_ACCOUNT_ID") # From nexus_config.py
TOKEN_FILE = "ts_tokens.json"

if not os.path.exists(TOKEN_FILE):
    print("NO TOKEN FILE")
    # Try to verify if we can get it from nexus_config? No, tokens are dynamic.
    exit()

with open(TOKEN_FILE, 'r') as f:
    tokens = json.load(f)

access_token = tokens.get("access_token")
url = f"https://api.tradestation.com/v3/brokerage/accounts/{ACCOUNT_ID}/balances"
headers = {"Authorization": f"Bearer {access_token}"}

print(f"CHECKING BALANCES FOR {ACCOUNT_ID}...")
try:
    r = requests.get(url, headers=headers, timeout=10)
    print(f"STATUS: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print("KEYS FOUND:")
        balances = data.get("Balances", [])
        if balances:
            b = balances[0]
            for k, v in b.items():
                print(f"{k}: {v}")
        else:
            print("No balances list found")
    else:
        print(f"RESPONSE: {r.text}")
except Exception as e:
    print(f"ERROR: {e}")
