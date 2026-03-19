import os
import requests
import json

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TICKER = "SPY"
STRIKE = 710.0
EXPIRY = "2026-01-16"

def debug_orats():
    url = "https://api.orats.io/datav2/live/strikes"
    params = { "token": ORATS_API_KEY, "ticker": TICKER }
    
    print(f"Fetching data for {TICKER}...")
    response = requests.get(url, params=params)
    data = response.json()
    
    strikes = data.get('data', [])
    candidates = [x for x in strikes if x.get('expirDate') == EXPIRY]
    
    if not candidates:
        print("No candidates found.")
        return

    contract = min(candidates, key=lambda x: abs(float(x['strike']) - STRIKE))
    
    print("\n=== RAW CONTRACT DATA ===")
    print(json.dumps(contract, indent=2))
    
    print("\n=== IV CHECK ===")
    print(f"iv: {contract.get('iv')}")
    print(f"smvVol: {contract.get('smvVol')}")
    print(f"impliedVol: {contract.get('impliedVol')}")

if __name__ == "__main__":
    debug_orats()
