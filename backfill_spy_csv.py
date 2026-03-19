import os
import csv
import datetime
import requests
import json

try: from nexus_config import ORATS_API_KEY
except: ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

def generate_spy_backfill():
    url = "https://api.orats.io/datav2/hist/strikes"
    headers = ['symbol', 'exp', 'dte', 'stk', 'underlying_price', 'type', 'vol', 'oi', 'delta', 'gamma', 'vega', 'theta', 'prem']
    
    today = datetime.date.today()
    dates_to_fetch = []
    days_back = 1
    while len(dates_to_fetch) < 5:
        d = today - datetime.timedelta(days=days_back)
        if d.weekday() < 5: # Monday-Friday
            dates_to_fetch.append(d.strftime("%Y-%m-%d"))
        days_back += 1
        
    print(f"Fetching SPY history for: {dates_to_fetch}")
    
    out_dir = "/root/snapshots_spy"
    os.makedirs(out_dir, exist_ok=True)
    
    for trade_date in dates_to_fetch:
        params = {
            'token': ORATS_API_KEY.strip(),
            'ticker': 'SPY',
            'tradeDate': trade_date
        }
        print(f"[{trade_date}] Requesting ORATS dataset...")
        try:
            r = requests.get(url, params=params, timeout=30)
            data = r.json().get('data', [])
        except Exception as e:
            print(f"Error fetching {trade_date}: {e}")
            continue
            
        if not data:
            print(f"No data for {trade_date}.")
            continue
            
        filename = os.path.join(out_dir, f"spy_snapshot_{trade_date}_235959.csv")
        with open(filename, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            count = 0
            for item in data:
                exp_date_str = item.get('expirDate')
                if not exp_date_str: continue
                
                try:
                    exp_date = datetime.datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                    quote_date = datetime.datetime.strptime(trade_date, "%Y-%m-%d").date()
                    dte = (exp_date - quote_date).days
                    if dte < 0: continue
                    
                    strike = float(item.get('strike', 0))
                    spot = float(item.get('stockPrice', 0))
                    
                    c_vol = int(item.get('callVolume', 0))
                    c_oi = int(item.get('callOpenInterest', 0))
                    c_d = float(item.get('callDelta') or item.get('delta') or 0)
                    c_g = float(item.get('callGamma') or item.get('gamma') or 0)
                    c_t = float(item.get('callTheta') or item.get('theta') or 0)
                    c_v = float(item.get('callVega') or item.get('vega') or 0)
                    
                    writer.writerow(['SPY', exp_date_str, dte, strike, spot, 'CALL', c_vol, c_oi, c_d, c_g, c_v, c_t, 0.0])
                    count += 1
                    
                    p_vol = int(item.get('putVolume', 0))
                    p_oi = int(item.get('putOpenInterest', 0))
                    p_d = float(item.get('putDelta') or 0)
                    if p_d == 0 and c_d != 0: p_d = c_d - 1.0
                    p_g = float(item.get('putGamma') or item.get('gamma') or 0)
                    p_t = float(item.get('putTheta') or item.get('theta') or 0)
                    p_v = float(item.get('putVega') or item.get('vega') or 0)
                    
                    writer.writerow(['SPY', exp_date_str, dte, strike, spot, 'PUT', p_vol, p_oi, p_d, p_g, p_v, p_t, 0.0])
                    count += 1
                except Exception as e:
                    pass
        print(f"Saved {count} records to {filename}")

if __name__ == "__main__":
    generate_spy_backfill()
