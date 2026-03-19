import requests, os, json
from datetime import datetime
UW_API_KEY = os.getenv("UNUSUAL_WHALES_API_KEY")
TICKER = "SPX"
STRIKE = 660
TYPE = "call"

def check_itm():
    url = "https://api.unusualwhales.com/api/screener/option-contracts"
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    
    print(f"Checking {TICKER} {TYPE} Strike {STRIKE} for next 10 days...")
    
    # Check 0-10 DTE
    for i in range(0, 10):
        params = {
            'ticker_symbol': TICKER,
            'min_dte': i,
            'max_dte': i,
            'type': TYPE,
            'min_strike': STRIKE,
            'max_strike': STRIKE
        }
        
        try:
            r = requests.get(url, headers=headers, params=params, timeout=10)
            data = r.json().get('data', [])
            
            if data:
                print(f"--- DTE {i} ---")
                for c in data:
                    print(f"Symbol: {c['option_symbol']} | OI: {c['open_interest']} | Vol: {c['volume']}")
            else:
                print(f"DTE {i}: No Data Found")
                
        except Exception as e:
            print(f"Error DTE {i}: {e}")

if __name__ == "__main__":
    check_itm()
