
import requests
import os
import json

UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
TICKER = "SPY"

def check_symbol_format():
    print("Fetching 1 result to check symbol format...")
    url = "https://api.unusualwhales.com/api/screener/option-contracts"
    params = {
        'ticker_symbol': TICKER,
        'limit': 1,
        'order': 'open_interest',
        'order_direction': 'desc'
    }
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        data = r.json().get('data', [])
        if data:
            print(f"Sample Row: {json.dumps(data[0], indent=2)}")
        else:
            print("No data.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_symbol_format()
