import os
import requests
import pandas as pd
import datetime
import mibian
import numpy as np

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
ORATS_URL = "https://api.orats.io/datav2/live/strikes"

def get_live_chain(ticker="SPY"):
    """
    Fetches live option chain from ORATS and transforms it into a long-format DataFrame.
    """
    params = {
        "token": ORATS_API_KEY,
        "ticker": ticker,
        "fields": "ticker,tradeDate,expirDate,strike,callBidPrice,callAskPrice,putBidPrice,putAskPrice,delta,gamma,theta,vega,smvVol,callVolume,putVolume,callOpenInterest,putOpenInterest,callValue,putValue,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,stockPrice"
    }
    
    try:
        resp = requests.get(ORATS_URL, params=params, timeout=25)
        resp.raise_for_status()
        data = resp.json().get('data', [])
        
        if not data:
            print(f"[WARN] No data returned from ORATS for {ticker}")
            return pd.DataFrame()

        # Transform Data (Melt)
        rows = []
        for r in data:
            # Common fields
            try:
                # Ensure Strict YYYY-MM-DD format
                expiry_str = pd.to_datetime(r.get('expirDate')).strftime('%Y-%m-%d')
            except:
                expiry_str = r.get('expirDate', '2000-01-01')
            
            strike = float(r.get('strike', 0))
            iv = float(r.get('smvVol', 0)) * 100 # Convert to %
            stock_price = float(r.get('stockPrice', 0))

            # SCALING: ORATS is per-share. 
            # We want to return per-share values so nexus_greeks.py can apply (100 * Qty).
            
            # Greeks (Robust Extraction)
            c_delta = float(r.get('callDelta') or r.get('delta', 0) or 0)
            p_delta = float(r.get('putDelta') or 0)
            
            # [FIX] REMOVE * 100 SCALING. 
            # nexus_greeks.py applies * 100 * Qty. 
            # If we scale here, we get * 10000. Bad.
            
            c_gamma = float(r.get('callGamma') or r.get('gamma', 0) or 0)
            p_gamma = float(r.get('putGamma') or r.get('gamma', 0) or 0)
            
            c_theta = float(r.get('callTheta') or r.get('theta', 0) or 0)
            p_theta = float(r.get('putTheta') or r.get('theta', 0) or 0)
            
            c_vega = float(r.get('callVega') or r.get('vega', 0) or 0)
            p_vega = float(r.get('putVega') or r.get('vega', 0) or 0)

            # CALL
            call_delta = c_delta
            
            # PUT (Synthetic Fallback if needed)
            put_delta = p_delta if p_delta != 0 else (c_delta - 1.0 if c_delta != 0 else 0)
            
            # MIBIAN FALLBACK logic
            # Use fallback if IV > 0 and Greeks are missing or suspicious
            try:
                dte_days = (datetime.date.fromisoformat(expiry_str) - datetime.date.today()).days
                if dte_days < 0.01: dte_days = 0.01
                
                # Check if we need fallback
                if (c_theta == 0 or abs(c_theta) < 0.01) and iv > 0 and stock_price > 0:
                     bs = mibian.BS([stock_price, strike, 0, dte_days], volatility=iv)
                     
                     if c_theta == 0 or abs(c_theta) < 0.01: c_theta = bs.callTheta * 100
                     if c_vega == 0 or abs(c_vega) < 0.01:  c_vega = bs.vega * 100
                     if c_gamma == 0 or abs(c_gamma) < 0.001: c_gamma = bs.gamma * 100
                     if c_delta == 0: c_delta = bs.callDelta
                     call_delta = c_delta # Update local var

                     if p_theta == 0 or abs(p_theta) < 0.01: p_theta = bs.putTheta * 100
                     if p_vega == 0 or abs(p_vega) < 0.01:  p_vega = bs.vega * 100
                     if p_gamma == 0 or abs(p_gamma) < 0.001: p_gamma = bs.gamma * 100
                     if put_delta == 0: put_delta = bs.putDelta

            except Exception as e: 
                pass

            # CALL Row
            rows.append({
                'strike': strike,
                'type': 'CALL',
                'expiry': expiry_str,
                'bid': float(r.get('callBidPrice', 0) or 0),
                'ask': float(r.get('callAskPrice', 0) or 0),
                'last': float(r.get('callValue', 0) or 0),
                'iv': iv,
                'delta': call_delta,
                'gamma': c_gamma,
                'theta': c_theta,
                'vega': c_vega,
                'volume': int(r.get('callVolume', 0) or 0),
                'open_interest': int(r.get('callOpenInterest', 0) or 0),
                'iv_rank': 50
            })
            
            # PUT Row
            rows.append({
                'strike': strike,
                'type': 'PUT',
                'expiry': expiry_str,
                'bid': float(r.get('putBidPrice', 0) or 0),
                'ask': float(r.get('putAskPrice', 0) or 0),
                'last': float(r.get('putValue', 0) or 0),
                'iv': iv,
                'delta': put_delta,
                'gamma': p_gamma,
                'theta': p_theta,
                'vega': p_vega,
                'volume': int(r.get('callVolume', 0) or 0),
                'open_interest': int(r.get('callOpenInterest', 0) or 0),
                'iv_rank': 50
            })
            
            # PUT Row
            rows.append({
                'strike': strike,
                'type': 'PUT',
                'expiry': expiry_str,
                'bid': float(r.get('putBidPrice', 0) or 0),
                'ask': float(r.get('putAskPrice', 0) or 0),
                'last': float(r.get('putValue', 0) or 0),
                'iv': iv,
                'delta': put_delta,
                'gamma': p_gamma,
                'theta': p_theta,
                'vega': p_vega,
                'volume': int(r.get('putVolume', 0) or 0),
                'open_interest': int(r.get('putOpenInterest', 0) or 0),
                'iv_rank': 50 
            })
            
        df = pd.DataFrame(rows)
        if df.empty: return df

        # 1. Filter Expired Rows
        # Ensure we only keep future expirations
        df['expiry_dt'] = pd.to_datetime(df['expiry'])
        df = df[df['expiry_dt'] > pd.Timestamp.now()]

        # 2. Recalculate DTE (Crucial fix for stale API data)
        # Use today's date to get accurate DTE
        # Fix: Ensure DTE is a float and never exactly 0.
        df['dte'] = (df['expiry_dt'] - pd.Timestamp.now()).dt.total_seconds() / 86400.0
        df['dte'] = df['dte'].clip(lower=0.01)
        
        # Drop temp column
        df = df.drop(columns=['expiry_dt'])

        print(f"[INFO] Contracts remaining after future-date filter: {len(df)}")
        return df

    except Exception as e:
        print(f"[ERROR] ORATS Fetch Failed: {e}")
        return pd.DataFrame()
