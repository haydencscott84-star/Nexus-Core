import os
import requests
import urllib.parse
import json

# --- CONFIGURATION (MATCHING TRADESTATION EXPLORER) ---
CLIENT_KEY = os.environ.get("TS_CLIENT_ID", "YOUR_TS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TS_CLIENT_SECRET", "YOUR_TS_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8080" 

# --- 1. GENERATE AUTH URL ---
base_url = "https://signin.tradestation.com/authorize"
params = {
    "response_type": "code",
    "client_id": CLIENT_KEY,
    "redirect_uri": REDIRECT_URI,
    "audience": "https://api.tradestation.com",
    "scope": "openid profile offline_access MarketData ReadAccount Trade OptionSpreads" 
}
auth_url = f"{base_url}?{urllib.parse.urlencode(params)}"

print("\n--- STEP 1: AUTHORIZATION ---")
print("1. COPY the link below.")
print("2. PASTE it into your browser (Chrome/Safari).")
print("3. Log in.")
print(f"\n{auth_url}\n")
print("After you login, you will see a 'Success' message or a connection error.")
print("LOOK AT THE URL BAR. It will look like: http://localhost:8080/?code=Po12345...")
print("COPY THAT ENTIRE URL AND PASTE IT BELOW.")

# --- INPUT LOOP ---
while True:
    print("\n---------------------------------------------------")
    print("WAIT! AFTER you log in, the browser address bar will change.")
    print("It will start with: http://localhost:8080/?code=...")
    print("---------------------------------------------------")
    code_url = input("PASTE THE RESULTING LOCALHOST URL HERE: ").strip()

    if "signin.tradestation.com" in code_url:
        print("\n❌ WRONG URL! You pasted the login link again.")
        print("Please log in first, wait for the redirect, and copy the NEW URL from the browser.")
        continue
        
    if "code=" not in code_url:
        print("\n❌ Invalid URL. It must contain '?code='")
        continue
        
    break

# Extract the 'code' parameter
auth_code = None
try:
    parsed = urllib.parse.urlparse(code_url)
    auth_code = urllib.parse.parse_qs(parsed.query)['code'][0]
except Exception as e:
    print(f"Error parsing code: {e}")
    exit()

# --- 2. EXCHANGE CODE FOR TOKENS ---
print("\n--- STEP 2: GENERATING TOKENS ---")
token_url = "https://signin.tradestation.com/oauth/token"
payload = {
    "grant_type": "authorization_code",
    "client_id": CLIENT_KEY,
    "client_secret": CLIENT_SECRET,
    "code": auth_code,
    "redirect_uri": REDIRECT_URI
}

headers = {"Content-Type": "application/x-www-form-urlencoded"}
response = requests.post(token_url, data=payload, headers=headers)

if response.status_code == 200:
    print("\nSUCCESS! New tokens.json created.")
    # Parsing to add expires_at for compatibility with TradeStationManager
    import time
    data = response.json()
    if 'expires_in' in data:
        data['expires_at'] = time.time() + int(data['expires_in']) - 60
        
    with open("ts_tokens.json", "w") as f:
        json.dump(data, f, indent=4)
    print("Saved to ts_tokens.json")
else:
    print(f"\nERROR: {response.text}")
