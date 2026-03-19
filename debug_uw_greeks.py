import requests
import json
import os

UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")
TICKER = "SPY"
EXPIRY = "2026-02-06" # Use an expiry from the portfolio

def fetch_chain_uw(ticker, expiry):
    url = f"https://api.unusualwhales.com/api/stock/{ticker}/greeks"
    params = { "expiry": expiry }
    headers = { "Authorization": f"Bearer {UW_API_KEY}" }
    
    print(f"Fetching {ticker} {expiry} from {url}...")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            greeks_list = data.get('data', [])
            print(f"Found {len(greeks_list)} items.")
            
            if len(greeks_list) > 0:
                print("--- SAMPLE ITEM 0 ---")
                print(json.dumps(greeks_list[0], indent=2))
                
                # Check for collisions
                strikes = [float(x.get('strike', 0)) for x in greeks_list]
                unique_strikes = set(strikes)
                print(f"Total Items: {len(strikes)} | Unique Strikes: {len(unique_strikes)}")
                
                if len(strikes) != len(unique_strikes):
                    print("⚠️ WARNING: Duplicate Strikes detected! API returns per-contract, not per-strike.")
                else:
                    print("✅ Strikes are unique. API likely returns per-strike view.")
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_chain_uw(TICKER, EXPIRY)
