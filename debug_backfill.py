import requests
import datetime
import pytz
import os
import json

# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ET = pytz.timezone('US/Eastern')
TICKERS_TO_SHOW = ["SPY", "SPX", "SPXW"]
PREMIUM_THRESHOLDS = {"SPY": 100000, "SPX": 250000, "SPXW": 250000, "DEFAULT": 50000}
MIN_DTE = 0; MAX_DTE = 45

def get_ny_time(): return datetime.datetime.now(ET)
def get_today_str(): return get_ny_time().strftime("%Y-%m-%d")

print("🔍 STARTING BACKFILL DIAGNOSTIC 🔍")
print(f"[*] API Key: {UW_API_KEY[:5]}...{UW_API_KEY[-5:]}")

# 1. Check Time
today_str = get_today_str()
print(f"[*] Calculated Today's Date (ET): {today_str}")

# 2. Make Request
url = "https://api.unusualwhales.com/api/screener/option-contracts"
headers = {"Authorization": f"Bearer {UW_API_KEY}"}

for t in TICKERS_TO_SHOW:
    print(f"\n--- Testing Ticker: {t} ---")
    th = PREMIUM_THRESHOLDS.get(t, 50000)
    p = {
        'ticker_symbol': t, 
        'order': 'premium', 
        'order_direction': 'desc', 
        'limit': 100, 
        'min_dte': MIN_DTE, 
        'max_dte': MAX_DTE, 
        'min_premium': th, 
        'date': today_str
    }
    print(f"[*] Params: {p}")
    
    try:
        r = requests.get(url, headers=headers, params=p, timeout=10)
        print(f"[*] Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json().get('data', [])
            print(f"[*] Row Count: {len(data)}")
            
            if len(data) == 0:
                print("[!] RESPONSE IS EMPTY.")
                
                # 3. Force Fix (Try Yesterday)
                print("[*] Attempting Force Fix: Trying Yesterday...")
                yesterday = (get_ny_time() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                p['date'] = yesterday
                print(f"[*] New Date: {yesterday}")
                
                r2 = requests.get(url, headers=headers, params=p, timeout=10)
                if r2.status_code == 200:
                    data2 = r2.json().get('data', [])
                    print(f"[*] Yesterday's Row Count: {len(data2)}")
                    if len(data2) > 0:
                        print("[SUCCESS] Found data for yesterday! The API likely hasn't updated for 'today' yet or it's a holiday/weekend.")
                        print(f"Sample: {data2[0]}")
                    else:
                        print("[!] Yesterday is ALSO empty.")
                        print(f"Raw Response: {r2.text[:500]}")
                else:
                    print(f"[!] Yesterday Request Failed: {r2.status_code}")
            else:
                print("[SUCCESS] Data found for today.")
                print(f"Sample: {data[0]}")
        else:
            print(f"[!] Request Failed. Response: {r.text}")
            
    except Exception as e:
        print(f"[!] Exception: {e}")

print("\n🏁 DIAGNOSTIC COMPLETE 🏁")
