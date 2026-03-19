import requests
import os
import json

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TICKER = "SPY"

def check():
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': TICKER}
    try:
        print(f"Fetching {url}...")
        r = requests.get(url, params=params, timeout=10)
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                print(f"Items: {len(data)}")
                first = data[0]
                print("KEYS:", list(first.keys()))
                print("SAMPLE:", json.dumps(first, indent=2))
            else:
                print("No data in response")
        else:
            print("Error response")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    check()
