import os

import requests
import json

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TICKER = "SPY"

def debug_ivrank():
    # User suggested: https://api.orats.io/datav2/ivrank
    url = "https://api.orats.io/datav2/ivrank"
    params = { "token": ORATS_API_KEY, "ticker": TICKER }
    
    print(f"Fetching IVRANK data for {TICKER}...")
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        print("\n=== RAW IVRANK RESPONSE ===")
        print(json.dumps(data, indent=2))
        
        if 'data' in data and len(data['data']) > 0:
            item = data['data'][0]
            print("\n=== KEY FIELDS CHECK ===")
            print(f"ivRank1y: {item.get('ivRank1y')}")
            print(f"ivPctile1y: {item.get('ivPctile1y')}")
            print(f"stockPrice: {item.get('stockPrice')}")
            print(f"last: {item.get('last')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_ivrank()
