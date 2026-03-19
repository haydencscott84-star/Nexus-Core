import os
import requests
import pandas as pd
import datetime
import mibian

TARGET_FILE = "/root/orats_connector.py"

NEW_CONTENT = """import requests
import pandas as pd
import datetime
import mibian
import numpy as np

# Updated to use optimized endpoints
ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
BASE_URL = "https://api.orats.io/datav2/live"

def get_live_chain(ticker="SPY", max_dte=60):
    \"\"\"
    Optimized Fetch: 
    1. Get Expirations
    2. Filter by max_dte (default 60)
    3. Fetch Strikes for specific expirations
    \"\"\"
    try:
        # Step 1: Get Expirations
        exp_url = f"{BASE_URL}/expirations"
        params = {'token': ORATS_API_KEY, 'ticker': ticker}
        
        print(f"[ORATS] Fetching expirations for {ticker}...")
        resp = requests.get(exp_url, params=params, timeout=10)
        resp.raise_for_status()
        
        # API returns list of date strings: ["2025-01-17", "2025-01-24", ...]
        expirations = resp.json().get('data', [])
        
        if not expirations:
            print("[ORATS] No expirations found.")
            return pd.DataFrame()

        # Filter Expirations
        target_expiries = []
        today = datetime.date.today()
        
        for exp_str in expirations:
            try:
                # exp_str is "YYYY-MM-DD" directly
                d_obj = datetime.date.fromisoformat(exp_str)
                dte = (d_obj - today).days
                if 0 <= dte <= max_dte:
                    target_expiries.append(exp_str)
            except Exception as e: 
                # print(f"Date Parse Err: {e}")
                pass
            
        if not target_expiries:
            print("[ORATS] No expirations within DTE range.")
            return pd.DataFrame()
            
        print(f"[ORATS] Fetching strikes for {len(target_expiries)} expirations (Max DTE: {max_dte})...")
        
        strk_url = f"{BASE_URL}/strikes/monthly"
        combined_expiry = ",".join(target_expiries)
        
        params = {
            'token': ORATS_API_KEY,
            'ticker': ticker,
            'expiry': combined_expiry,
            "fields": "ticker,tradeDate,expirDate,strike,callBidPrice,callAskPrice,putBidPrice,putAskPrice,delta,gamma,theta,vega,smvVol,callVolume,putVolume,callOpenInterest,putOpenInterest,callValue,putValue,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,stockPrice"
        }
        
        resp = requests.get(strk_url, params=params, timeout=25) 
        resp.raise_for_status()
        data = resp.json().get('data', [])
        
        if not data:
            print("[ORATS] No strike data returned.")
            return pd.DataFrame()

        # Transform Data
        rows = []
        for r in data:
            try:
                expiry_str = pd.to_datetime(r.get('expirDate')).strftime('%Y-%m-%d')
            except: continue
            
            strike = float(r.get('strike', 0))
            # iv = float(r.get('smvVol', 0)) * 100 
            stock_price = float(r.get('stockPrice', 0))

            # SCALING
            c_delta = float(r.get('callDelta') or r.get('delta', 0) or 0)
            p_delta = float(r.get('putDelta') or 0)
            c_gamma = float(r.get('callGamma') or r.get('gamma', 0) or 0) * 100
            p_gamma = float(r.get('putGamma') or r.get('gamma', 0) or 0) * 100
            
            # Simple Processing
            call_delta = c_delta
            put_delta = p_delta if p_delta != 0 else (c_delta - 1.0 if c_delta != 0 else 0)
            
            # CALL
            rows.append({
                'strike': strike, 'type': 'CALL', 'expiry': expiry_str,
                'delta': call_delta, 'gamma': c_gamma, 'stockPrice': stock_price
            })
            # PUT
            rows.append({
                'strike': strike, 'type': 'PUT', 'expiry': expiry_str,
                'delta': put_delta, 'gamma': p_gamma, 'stockPrice': stock_price
            })

        df = pd.DataFrame(rows)
        # Recalc DTE for dashboard compatibility
        df['expiry_dt'] = pd.to_datetime(df['expiry'])
        df['dte'] = (df['expiry_dt'] - pd.Timestamp.now()).dt.total_seconds() / 86400.0
        df = df.drop(columns=['expiry_dt'])
        
        print(f"[ORATS] Loaded {len(df)} contracts.")
        return df

    except Exception as e:
        print(f"[ERROR] ORATS Optimized Fetch Failed: {e}")
        return pd.DataFrame()
"""

def apply_fix():
    print(f"Overwriting {TARGET_FILE} with optimized logic...")
    with open(TARGET_FILE, 'w') as f:
        f.write(NEW_CONTENT)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
