import os
import requests
import json
import datetime

UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")
BASE_URL = "https://api.unusualwhales.com"

# Tickers to test
# UW likely uses VIX, not ^VIX
TICKERS = {
    "SPY": "SPY",
    # "RSP": "RSP",
    # "^VIX": "VIX",
    # "^VIX3M": "VIX3M", 
    # "^VVIX": "VVIX"
}

def test_uw_history(ticker, uw_symbol):
    print(f"Testing {ticker} (as {uw_symbol})...")
    
    # Endpoint: /api/stock/{ticker}/ohlc/{candle_size}
    url = f"{BASE_URL}/api/stock/{uw_symbol}/ohlc/1d"
    
    headers = {
        "Authorization": f"Bearer {UW_API_KEY}",
        "Accept": "application/json"
    }
    
    params = {
        "limit": 10 # Just fetch a few to verify
    }
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                print(f"✅ SUCCESS: Found {len(data)} rows.")
                print(f"   Sample: {data[0]}")
                return True
            else:
                print(f"⚠️ EMPTY: No data returned.")
                return False
        else:
            print(f"❌ FAIL: Status {r.status_code}")
            print(f"   Response: {r.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    print("🔍 Unusual Whales Historical Data Probe")
    print("=======================================")
    
    results = {}
    for t, sym in TICKERS.items():
        results[t] = test_uw_history(t, sym)
        print("-" * 30)
        
    print("\nSummary:")
    for t, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {t}")

if __name__ == "__main__":
    main()
