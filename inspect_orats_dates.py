import requests
import os
import datetime

# Hardcoded for debug as seen in viewer_dash_nexus.py
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"

def get_orats_expiries():
    api_url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': TICKER}
    
    print(f"Fetching ORATS strikes for {TICKER}...")
    try:
        response = requests.get(api_url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        result_data = data.get('data', [])
        
        if not result_data:
            print("No data returned.")
            return

        # Extract unique expiries
        expiries = set()
        for item in result_data:
            exp = item.get('expirDate')
            if exp:
                expiries.add(exp)
        
        sorted_expiries = sorted(list(expiries))
        print(f"\nFound {len(sorted_expiries)} unique expiries:")
        for e in sorted_expiries:
            print(f" - {e}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    get_orats_expiries()
