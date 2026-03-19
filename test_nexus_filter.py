import requests
import json
import os
import datetime
import pytz
import re

UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ET = pytz.timezone('US/Eastern')
UTC = pytz.utc

def get_ny_time(): return datetime.datetime.now(ET)
def get_trading_date(): 
    d = get_ny_time().date()
    while d.weekday() >= 5: d -= datetime.timedelta(days=1)
    return d
    
url = "https://api.unusualwhales.com/api/option-trades/flow-alerts"
p = {'ticker_symbol': 'SPY', 'limit': 5, 'min_premium': 50000, 'min_dte': 0, 'max_dte': 35}
h = {"Authorization": f"Bearer {UW_API_KEY}"}

print("Fetching:", url, p)
resp = requests.get(url, params=p, headers=h)
data = resp.json().get('data', [])

if not data:
    print("NO DATA FROM API!")
else:
    for i in data:
        print("\n--- NEW ITEM ---")
        print("Ticker:", i.get('ticker'), i.get('underlying_symbol'))
        ts = i.get('executed_at') or i.get('created_at') or i.get('timestamp') or i.get('date')
        print("TS raw:", ts)
        ts_val = 0.0
        if isinstance(ts, str): ts_val = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
        else: ts_val = float(ts)
        if ts_val > 100_000_000_000: ts_val = ts_val / 1000.0
        print("ts_val:", ts_val)
        
        try:
            d = datetime.datetime.fromtimestamp(ts_val, tz=UTC).astimezone(ET).date()
            print("date from ts:", d, "get_trading_date:", get_trading_date(), "is_from_today:", d == get_trading_date())
        except Exception as e: print("is_today Error:", e)
        
        prem = float(i.get('total_premium') or i.get('premium') or 0)
        if prem == 0:
             sz = float(i.get('total_size') or i.get('size') or 0)
             pr = float(i.get('price') or i.get('p') or 0)
             prem = sz * pr * 100
        print("Premium:", prem)
        
        chain = i.get('option_chain') or i.get('symbol')
        print("Chain:", chain)
        if chain:
            match = re.search(r'(\d{6})([CP])([\d\.]+)$', chain)
            print("REGEX:", bool(match), match.groups() if match else "")
