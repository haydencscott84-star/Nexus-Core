import os
import requests
import json

def test_orats_auth():
    print("--- DEBUGGING ORATS AUTH ---")
    
    # 1. Check Env Var / Fallback
    api_key = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
    masked_key = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****"
    print(f"✅ API Key: {masked_key}")

    # 2. Test Request
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': api_key, 'ticker': 'SPY'}
    
    print(f"Testing URL: {url}")
    
    try:
        r = requests.get(url, params=params, timeout=10)
        print(f"Status Code: {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            items = data.get('data', [])
            count = len(items)
            print(f"✅ SUCCESS! Retrieved {count} strikes.")
            
            if count > 0:
                first_item = items[0]
                print(f"Sample Item Keys: {list(first_item.keys())}")
                # Print first item to see structure
                print(json.dumps(first_item, indent=2))
        else:
            print(f"❌ FAILED: {r.status_code}")
            print(f"Response: {r.text}")
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")

if __name__ == "__main__":
    test_orats_auth()
