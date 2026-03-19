import os

import requests, datetime, os
from nexus_config import get_et_now
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")

def get_trading_date():
    d = get_et_now().date()
    from datetime import timedelta
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d

today_str = get_trading_date().strftime("%Y-%m-%d")
print(f"Querying Date: {today_str}")

url = "https://api.unusualwhales.com/api/option-trades/flow-alerts"
headers = {"Authorization": f"Bearer {UW_API_KEY}"}

# Test 1: Date Parameter
print("\n[Test 1] Query with date param...")
for tkr in ['SPY', 'SPX', 'SPXW']:
    print(f"\nScanning {tkr}...")
    p = {'ticker_symbol': tkr, 'limit': 5, 'date': today_str}
    try:
        r = requests.get(url, headers=headers, params=p, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json().get('data', [])
            print(f"Count: {len(data)}")
            for i in data[:3]:
                ts = i.get('created_at') or i.get('timestamp')
                print(f"  - TS: {ts}")
                prem = i.get('premium') or i.get('total_premium')
                print(f"  - Prem: {prem}")
    except Exception as e: print(e)

# Test 2: NO Date Parameter
print("\n[Test 2] Query WITHOUT date param...")
p = {'ticker_symbol': 'SPY', 'limit': 10}
try:
    r = requests.get(url, headers=headers, params=p, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json().get('data', [])
        print(f"Count: {len(data)}")
        for i in data[:3]:
            ts = i.get('created_at') or i.get('timestamp')
            print(f"  - TS: {ts}")
except Exception as e: print(e)
