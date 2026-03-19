import requests
import os
import json

UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
TICKER = "SPY"

def check_gap():
    url = "https://api.unusualwhales.com/api/screener/option-contracts"
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    
    # Target the missing range from screenshot
    # Strike 700 was 0.0k
    params = {
        'ticker_symbol': TICKER,
        'limit': 500,
        'order': 'open_interest',
        'order_direction': 'desc',
        'min_dte': 0,
        'max_dte': 3,
        'min_strike': 695,
        'max_strike': 705,
        'type': 'put'
    }
    
    print(f"Requesting Gap Check: {params}")
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        print(f"Status: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json().get('data', [])
            print(f"Rows Returned: {len(data)}")
            
            # Print Non-Zero OI
            found = False
            for row in data:
                oi = float(row.get('open_interest', 0))
                strike = float(row.get('strike', 0))
                
                # Robust Parse if 0
                if strike == 0:
                    sym = row.get('option_symbol', '')
                    try: strike = float(sym[-8:]) / 1000
                    except: pass
                    
                if strike >= 698 and strike <= 702:
                    print(f"Strike {strike} Put OI: {oi}")
                    if oi > 0: found = True
            
            if not found:
                print("CRITICAL: API explicitly returns 0 OI for this range.")
        else:
            print(r.text)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_gap()
