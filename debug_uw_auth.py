import os
import requests
import json

def test_uw_auth():
    print("--- DEBUGGING UNUSUAL WHALES AUTH ---")
    
    # 1. Check Env Var
    api_key = os.getenv('UNUSUAL_WHALES_API_KEY')
    if not api_key:
        print("❌ ERROR: 'UNUSUAL_WHALES_API_KEY' environment variable is NOT set.")
        return

    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
    print(f"✅ API Key Found: {masked_key}")

    # 2. Test Request
    url = "https://api.unusualwhales.com/api/screener/option-contracts"
    # Minimal params for a lightweight check
    params = {'ticker_symbol': 'SPY', 'min_volume': 100, 'min_dte': 7, 'max_dte': 45}
    headers = {'Authorization': f'Bearer {api_key}'}

    print(f"Testing URL: {url}")
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', [])
            count = len(items)
            print(f"✅ SUCCESS! Retrieved {count} contracts.")
            
            if count > 0:
                first_item = items[0]
                print(f"Sample Item Keys: {list(first_item.keys())}")
                print(f"Sample Item: {json.dumps(first_item, indent=2)}")
        elif r.status_code == 401:
            print("❌ FAILED: 401 Unauthorized. Your API Key is invalid or expired.")
            print(f"Response: {r.text}")
        else:
            print(f"⚠️ FAILED: {r.status_code}")
            print(f"Response: {r.text}")
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    test_uw_auth()
