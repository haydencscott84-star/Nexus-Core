import os
import requests, json, os

ACCOUNT_ID = os.environ.get("TS_ACCOUNT_ID", "YOUR_ACCOUNT_ID")
TOKEN_FILE = "ts_tokens.json"

if not os.path.exists(TOKEN_FILE):
    print("NO TOKEN FILE")
    exit()

with open(TOKEN_FILE, 'r') as f:
    tokens = json.load(f)

access_token = tokens.get("access_token")
url = f"https://api.tradestation.com/v3/brokerage/accounts/{ACCOUNT_ID}/positions"
headers = {"Authorization": f"Bearer {access_token}"}

print(f"CHECKING ACCOUNT {ACCOUNT_ID}...")
try:
    r = requests.get(url, headers=headers, timeout=10)
    print(f"STATUS: {r.status_code}")
    print(f"RESPONSE: {r.text}")
except Exception as e:
    print(f"ERROR: {e}")
