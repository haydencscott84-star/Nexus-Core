import os
import requests
import json
import datetime

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

# Tickers to test
# Note: ORATS might use different symbols for indices.
TICKERS = {
    "SPY": "SPY",
    "RSP": "RSP",
    "^VIX": "VIX",    # ORATS likely uses VIX, not ^VIX
    "^VIX3M": "VIX3M", # Guessing
    "^VVIX": "VVIX"    # Guessing
}

def test_history(ticker, orats_symbol):
    print(f"Testing {ticker} (as {orats_symbol})...")
    
    # Endpoint: /datav2/hist/dailies (Historical Dailies)
    # Docs implies: https://api.orats.io/datav2/hist/dailies
    url = "https://api.orats.io/datav2/hist/dailies"
    
    # Calculate 6 months ago
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=180)
    
    params = {
        "token": ORATS_API_KEY,
        "ticker": orats_symbol,
        "tradeDate[gte]": start_date.strftime("%Y-%m-%d"),
        "tradeDate[lte]": end_date.strftime("%Y-%m-%d"),
        "fields": "tradeDate,cls" # We need Close price
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            rows = data.get('data', [])
            if rows:
                print(f"✅ SUCCESS: Found {len(rows)} rows.")
                print(f"   First: {rows[0]}")
                print(f"   Last:  {rows[-1]}")
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
    print("🔍 ORATS Historical Data Probe")
    print("==============================")
    
    results = {}
    for t, sym in TICKERS.items():
        results[t] = test_history(t, sym)
        print("-" * 30)
        
    print("\nSummary:")
    for t, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {t}")

if __name__ == "__main__":
    main()
