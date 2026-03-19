import os

import requests
import json

# Key from orats_connector.py
ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
ORATS_URL = "https://api.orats.io/datav2/live/strikes"

def check_keys():
    params = {
        "token": ORATS_API_KEY,
        "ticker": "SPY",
        # Requesting EVERYTHING I can think of to see what sticks
        # But actually, let's request a minimal set + the problematic ones to see what comes back
        # If I request fields that don't exist, does it ignore them or error? Usually ignores.
        # But I want to see ALL available fields. 
        # ORATS documentation says fetching without 'fields' might return defaults? 
        # Let's try fetching with NO fields param to see default payload, 
        # OR fetch with the 'fields' we currently use to see which ones are null.
        "fields": "ticker,strike,expirDate,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,smvVol"
    }
    
    try:
        print(f"Fetching {ORATS_URL}...")
        resp = requests.get(ORATS_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        
        items = data.get('data', [])
        if not items:
            print("No data returned.")
            return

        print(f"Returned {len(items)} items.")
        
        # Find specific expiry
        atm_item = next((i for i in items if i.get('expirDate') == '2025-12-24' and 680 <= i.get('strike', 0) <= 690), None)
        
        if atm_item:
             print("\n--- DEC 24 ITEM (Strike ~685) ---")
             for k, v in atm_item.items():
                 print(f"{k}: {v}")
        else:
             print("No ATM item found.")
             # Fallback to first item
             print("\n--- FIRST ITEM ---")
             for k, v in items[0].items():
                 print(f"{k}: {v}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_keys()
