import requests
import os
import datetime

# Hardcoded Key from spx_profiler_nexus.py
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")

def check_usage():
    # Use a known valid endpoint from nexus_greeks.py
    url = "https://api.unusualwhales.com/api/stock/SPY/greeks"
    
    # Use next Friday as a safe expiry guess
    expiry = "2026-01-23" 
    params = { "expiry": expiry }
    headers = { "Authorization": f"Bearer {UW_API_KEY}" }
    
    print(f"--- CHECKING UW API USAGE ({url}) ---")
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        # Extract headers regardless of status code (429 often has them)
        limit = response.headers.get('x-uw-token-req-limit', 'UNKNOWN')
        count = response.headers.get('x-uw-daily-req-count', 'UNKNOWN')
        reset = response.headers.get('x-uw-req-reset', 'UNKNOWN')
        
        print(f"Daily Count: {count}")
        print(f"Daily Limit: {limit}")
        print(f"Reset In:    {reset}s")
        
        if response.status_code == 429:
            print("⚠️ RATE LIMITED (429)")
        elif response.status_code == 200:
            data = response.json()
            items = len(data.get('data', []))
            print(f"✅ Success. Returned {items} strikes.")
        else:
            print(f"❌ Error: {response.text[:200]}")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    check_usage()
