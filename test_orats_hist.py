import os
import requests
import json
import time

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

def test_endpoint(url, trade_date):
    print(f"\nTesting {url} for date {trade_date}")
    params = {
        'token': ORATS_API_KEY,
        'ticker': 'SPY',
        'tradeDate': trade_date
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                print(f"Success! Received {len(data)} records.")
                sample = data[0]
                print(f"Params used: {params}")
                print(f"Sample Trade Date in Response: {sample.get('tradeDate')}")
                print(f"Sample Expiration: {sample.get('expirDate')}")
                print(f"Sample Stock Price: {sample.get('stockPrice')}")
                print(f"Sample Call Volume: {sample.get('callVolume')}")
            else:
                print("Empty data array returned.")
        else:
            print(f"HTTP {r.status_code}: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

test_endpoint("https://api.orats.io/datav2/strikes", "2026-03-09")
time.sleep(1)
test_endpoint("https://api.orats.io/datav2/hist/strikes", "2026-03-09")
time.sleep(1)
# Some providers use "date" instead of "tradeDate"
print("\nTesting with 'date' parameter instead of 'tradeDate'")
params_date = {'token': ORATS_API_KEY, 'ticker': 'SPY', 'date': '2026-03-09'}
r = requests.get("https://api.orats.io/datav2/strikes", params=params_date)
print(f"Status: {r.status_code}")
if r.status_code == 200 and r.json().get('data'):
    print(f"Trade Date in Response: {r.json()['data'][0].get('tradeDate')}")
