
import requests
import os
import json

# Key from analyze_snapshots.py
ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

def debug_orats():
    print("Fetching ORATS data...")
    api_url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    
    try:
        resp = requests.get(api_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        items = data.get('data', [])
        if not items:
            print("No data found.")
            return

        # Print keys of the first item
        first_item = items[0]
        print(f"\n[ORATS Response Keys] ({len(items)} items total)")
        print(json.dumps(list(first_item.keys()), indent=2))
        
        # Check specific Greek values
        print("\n[Sample Values]")
        print(f"Strike: {first_item.get('strike')}")
        print(f"callVega: {first_item.get('callVega')}")
        print(f"callTheta: {first_item.get('callTheta')}")
        print(f"vega: {first_item.get('vega')}")
        print(f"theta: {first_item.get('theta')}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_orats()
