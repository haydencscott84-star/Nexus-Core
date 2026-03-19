import requests
import datetime
import pytz
import json
import os

# CONFIG FROM V1 SCRIPT
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
URL = "https://api.unusualwhales.com/api/screener/option-contracts"
ET = pytz.timezone('US/Eastern')

def get_today_str():
    return datetime.datetime.now(ET).strftime("%Y-%m-%d")

def test_fetch():
    print(f"--- DEBUGGING NEXUS SWEEPS V1 ---")
    print(f"API Key: {UW_API_KEY[:5]}...{UW_API_KEY[-5:]}")
    print(f"URL: {URL}")
    
    today = get_today_str()
    print(f"Date: {today}")
    
    headers = {"Authorization": f"Bearer {UW_API_KEY}"}
    
    # TEST 1: SPY with Standard Thresholds
    params = {
        'ticker_symbol': 'SPY',
        'order': 'premium',
        'order_direction': 'desc',
        'limit': 10,
        'min_dte': 0,
        'max_dte': 45,
        'min_premium': 100000, # Standard V1 Threshold
        'date': today
    }
    
    print(f"\n[TEST 1] Fetching SPY (Prem > $100k)...")
    try:
        r = requests.get(URL, headers=headers, params=params, timeout=10)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            results = data.get('data', []) # Adjust based on actual response structure
            # API might return list directly or dict with 'results'
            if isinstance(data, list): results = data
            elif isinstance(data, dict) and 'results' in data: results = data['results']
            
            print(f"Result Count: {len(results)}")
            if len(results) > 0:
                print("✅ DATA RECEIVED")
                print(f"Sample: {results[0]}")
            else:
                print("⚠️ NO DATA FOUND (Check Market Hours / Thresholds)")
        else:
            print(f"❌ API ERROR: {r.text}")
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

    # TEST 2: SPY with LOWER Thresholds (Connectivity Check)
    params['min_premium'] = 1000 # Very low to ensure data exists
    print(f"\n[TEST 2] Fetching SPY (Prem > $1k - Connectivity Check)...")
    try:
        r = requests.get(URL, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            results = data.get('data', [])
            if isinstance(data, list): results = data
            elif isinstance(data, dict) and 'results' in data: results = data['results']
            
            print(f"Result Count: {len(results)}")
            if len(results) > 0:
                print("✅ CONNECTIVITY OK (Data exists at lower thresholds)")
            else:
                print("❌ NO DATA EVEN AT LOW THRESHOLDS (API/Date Issue?)")
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    test_fetch()
