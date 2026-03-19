import os
import requests
import time
import json

API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
URL = "https://api.orats.io/datav2/live/strikes"

def test_conn():
    print(f"📡 Testing Connectivity to: {URL}")
    print(f"🔑 Key: ...{API_KEY[-4:]}")
    
    start = time.time()
    try:
        # Simple Request for SPY
        params = {"token": API_KEY, "ticker": "SPY", "fields": "ticker,strike,delta"}
        print("⏳ Sending Request (Timeout=10s)...")
        
        resp = requests.get(URL, params=params, timeout=10)
        
        elapsed = time.time() - start
        print(f"✅ Response Received in {elapsed:.2f}s")
        print(f"🔢 Status Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json().get('data', [])
            print(f"📊 Data Rows: {len(data)}")
            if len(data) > 0:
                print(f"📝 Sample: {data[0]}")
        else:
            print(f"❌ Error Output: {resp.text}")
            
    except Exception as e:
        print(f"💥 EXCEPTION: {e}")

if __name__ == "__main__":
    test_conn()
