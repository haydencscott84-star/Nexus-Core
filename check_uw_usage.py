import requests
import os

UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")

def check_usage():
    url = f"https://api.unusualwhales.com/api/stock/SPY/quote"
    headers = { "Authorization": f"Bearer {UW_API_KEY}" }
    
    print("--- CHECKING UW API USAGE ---")
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        limit = response.headers.get('x-uw-token-req-limit', 'UNKNOWN')
        count = response.headers.get('x-uw-daily-req-count', 'UNKNOWN')
        reset = response.headers.get('x-uw-req-reset', 'UNKNOWN')
        
        print(f"Daily Count: {count}")
        print(f"Daily Limit: {limit}")
        print(f"Reset In:    {reset}s")
        
        if response.status_code == 429:
            print("⚠️ RATE LIMITED (429)")
        elif response.status_code == 200:
            print("✅ API Available")
        else:
            print(f"❌ Error: {response.text}")

    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    check_usage()
