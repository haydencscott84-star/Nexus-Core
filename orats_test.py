import os
import requests
import json

# --- CONFIGURATION ---
# The API Key you want to test
NEW_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY") 
TICKER = "SPY"

def test_endpoint(name, url, params):
    """
    Helper function to hit an API endpoint and report status.
    """
    print(f"--- Testing {name} ---")
    print(f"URL: {url}")
    
    try:
        # Send request with a 10-second timeout
        response = requests.get(url, params=params, timeout=10)
        status = response.status_code
        
        # CASE 1: SUCCESS
        if status == 200:
            data = response.json()
            # Handle potential differences in response structure (list vs dict)
            if isinstance(data, dict) and 'data' in data:
                items = data['data']
            else:
                items = data

            count = len(items) if items else 0
            print(f"✅ SUCCESS (200 OK). Retrieved {count} records.")
            
            # Print a snippet of the first record to verify data integrity
            if count > 0:
                first = items[0] if isinstance(items, list) else items
                keys = list(first.keys())[:5] if isinstance(first, dict) else "N/A"
                print(f"   Sample fields: {keys}")
            return True

        # CASE 2: FORBIDDEN (Key valid, but missing permissions)
        elif status == 403:
            print(f"❌ FAILED (403 Forbidden).")
            print(f"   Analysis: Your API key is valid, but it lacks permission for this specific data.")
            print(f"   Response snippet: {response.text[:200]}")
            return False

        # CASE 3: UNAUTHORIZED (Key invalid)
        elif status == 401:
            print(f"❌ FAILED (401 Unauthorized).")
            print(f"   Analysis: The API key is invalid, expired, or typo'd.")
            return False

        # CASE 4: OTHER ERROR
        else:
            print(f"⚠️ ERROR ({status}): {response.text[:300]}")
            return False

    except Exception as e:
        print(f"💀 CRITICAL ERROR (Connection/Python): {e}")
        return False
    finally:
        print("-" * 40 + "\n")

def run_diagnostics():
    print(f"\n🔎 Starting ORATS Connection Test for {TICKER}...")
    print(f"🔑 Key in use: {NEW_API_KEY[:8]}...{NEW_API_KEY[-4:]}")
    print("="*60 + "\n")
    
    # ---------------------------------------------------------
    # TEST 1: Delayed Summaries 
    # (Lowest barrier to entry. Should work on almost any paid plan)
    # ---------------------------------------------------------
    delayed_params = { 'token': NEW_API_KEY, 'ticker': TICKER }
    delayed_success = test_endpoint(
        "1. Delayed Summaries (Basic Access)",
        "https://api.orats.io/datav2/summaries",
        delayed_params
    )
    
    # ---------------------------------------------------------
    # TEST 2: Historical Data 
    # (Usually included in standard tiers)
    # ---------------------------------------------------------
    hist_params = { 
        'token': NEW_API_KEY, 
        'ticker': TICKER, 
        'tradeDate': '2023-11-01' # Testing a specific past date
    }
    hist_success = test_endpoint(
        "2. Historical Daily Price",
        "https://api.orats.io/datav2/hist/dailies",
        hist_params
    )
    
    # ---------------------------------------------------------
    # TEST 3: Live Summaries 
    # (Requires 'Live Data' add-on)
    # ---------------------------------------------------------
    live_sum_params = { 'token': NEW_API_KEY, 'ticker': TICKER }
    live_summary_success = test_endpoint(
        "3. Live Summaries (Requires Live Add-on)",
        "https://api.orats.io/datav2/live/summaries",
        live_sum_params
    )
    
    # ---------------------------------------------------------
    # TEST 4: Live Strikes 
    # (CRITICAL for your Dashboard/GEX. High permission level.)
    # ---------------------------------------------------------
    live_str_params = { 'token': NEW_API_KEY, 'ticker': TICKER }
    live_strikes_success = test_endpoint(
        "4. Live Strikes (GEX Source)",
        "https://api.orats.io/datav2/live/strikes",
        live_str_params
    )
    
    # ---------------------------------------------------------
    # FINAL REPORT
    # ---------------------------------------------------------
    print("📊 DIAGNOSTIC REPORT")
    print("="*60)
    print(f"Delayed Data:   {'✅ PASS' if delayed_success else '❌ FAIL'}")
    print(f"Historical:     {'✅ PASS' if hist_success else '❌ FAIL'}")
    print(f"Live Summaries: {'✅ PASS' if live_summary_success else '❌ FAIL'}")
    print(f"Live Strikes:   {'✅ PASS' if live_strikes_success else '❌ FAIL'}")
    print("="*60 + "\n")

    if delayed_success and hist_success and live_strikes_success:
        print("🚀 CONCLUSION: GREEN LIGHT.")
        print("Your API key is fully active. You can run your dashboard.")
    elif delayed_success and not live_strikes_success:
        print("⚠️ CONCLUSION: PARTIAL ACCESS.")
        print("Your key works for basic data but is blocked from Live Strikes.")
        print("Likely Cause: You need to sign the OPRA/Cboe agreements on the ORATS dashboard.")
    elif not delayed_success and not hist_success:
        print("🛑 CONCLUSION: DEAD KEY.")
        print("This key has no permissions attached. Contact ORATS support.")
    else:
        print("⚠️ CONCLUSION: MIXED RESULTS.")
        print("See individual test outputs above.")

if __name__ == "__main__":
    run_diagnostics()