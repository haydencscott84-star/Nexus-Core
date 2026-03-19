import os

import requests, json

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TICKER = "SPY"

def probe_orats_core():
    # Attempt to fetch 'cores' which usually has IV, IVR, etc.
    url = "https://api.orats.io/datav2/cores"
    params = { "token": ORATS_API_KEY, "ticker": TICKER }
    
    print(f"Fetching ORATS Core data for {TICKER}...")
    try:
        r = requests.get(url, params=params)
        if r.status_code == 200:
            data = r.json()
            if "data" in data and len(data["data"]) > 0:
                core = data["data"][0]
                print("\n=== ORATS CORE DATA (snippet) ===")
                # Print IV related keys
                for k, v in core.items():
                    if "iv" in k.lower() or "rank" in k.lower() or "percentile" in k.lower():
                        print(f"{k}: {v}")
            else:
                print("No core data found.")
        else:
            print(f"Error: {r.status_code} {r.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    probe_orats_core()
