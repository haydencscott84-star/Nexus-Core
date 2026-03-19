import os
import requests
import pandas as pd

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
BASE_URL = "https://api.orats.io/datav2/live"

def debug_exp():
    url = f"{BASE_URL}/expirations"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    print("Fetching expirations...")
    resp = requests.get(url, params=params)
    data = resp.json().get('data', [])
    print(f"Raw Count: {len(data)}")
    if data:
        print("First 5 records:")
        for r in data[:5]:
            print(r)
            
if __name__ == "__main__":
    debug_exp()
