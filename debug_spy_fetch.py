
import requests
import json
import os

# Hardcoded fallback key if env var missing (matching analyze_snapshots)
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

def debug_fetch():
    endpoint_type = 'strikes'
    api_url = f"https://api.orats.io/datav2/live/{endpoint_type}"
    
    # EXACT params from analyze_snapshots.py
    params = {
        'token': ORATS_API_KEY.strip(), 
        'ticker': 'SPY',
        'fields': 'ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBid,callAsk,putBid,putAsk'
    }
    
    print(f"Fetching: {api_url}")
    print(f"Params: {params}")
    
    try:
        response = requests.get(api_url, params=params, timeout=15)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            return

        data = response.json()
        result_data = data.get('data', [])
        
        print(f"Rows returned: {len(result_data)}")
        
        if result_data:
            # Inspect first row keys
            print("\n--- FIRST ROW KEYS ---")
            first_row = result_data[0]
            print(list(first_row.keys()))
            
            # Find DTE > 30 Strikes (approx 680-685)
            print("\n--- DTE > 30 ATM SAMPLE (680-685) ---")
            from datetime import datetime, timedelta
            future_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
            
            atm_rows = [r for r in result_data if 680 <= float(r.get('strike', 0)) <= 685 and r.get('expirDate') > future_date]
            
            if not atm_rows:
                print("No ATM DTE > 30 rows found?")
                # Dump arbitrary DTE > 30
                long_rows = [r for r in result_data if r.get('expirDate') > future_date]
                atm_rows = long_rows[:5]
                
            for i, row in enumerate(atm_rows[:5]):
                print(f"Row {i} (Strike {row.get('strike')} Exp {row.get('expirDate')}):")
                # Check Call Theta/Vega
                c_theta = row.get('callTheta')
                theta = row.get('theta')
                vega = row.get('vega')
                iv = row.get('smvVol')
                
                print(f"  callTheta: {c_theta}")
                print(f"  theta: {theta}")
                print(f"  vega: {vega}")
                print(f"  IV (smvVol): {iv}")
                
                print("-" * 20)
                
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    debug_fetch()
