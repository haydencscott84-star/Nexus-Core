import requests
import datetime
import pytz
import os

UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")
ET = pytz.timezone('US/Eastern')

def get_trading_date():
    d = datetime.datetime.now(ET).date()
    # today is Monday 26th.
    return d.strftime("%Y-%m-%d")

today = get_trading_date()
print(f"Querying for Date: {today}")

url = "https://api.unusualwhales.com/api/option-trades/flow-alerts"
headers = {"Authorization": f"Bearer {UW_API_KEY}"}
params = {
    'ticker_symbol': 'SPY', 
    'limit': 10, 
    'min_premium': 50000, 
    'min_dte': 0, 
    'max_dte': 60, 
    'date': today
}

try:
    r = requests.get(url, headers=headers, params=params, timeout=10)
    print(f"Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json().get('data', [])
        print(f"Count: {len(data)}")
        if data:
            print("First Item:")
            print(data[0])
            ts = data[0].get('executed_at') or data[0].get('created_at')
            print(f"Timestamp raw: {ts}")
    else:
        print(f"Error: {r.text}")
except Exception as e:
    print(f"Exception: {e}")
