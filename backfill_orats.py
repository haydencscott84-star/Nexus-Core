import os
import json
import time
import datetime
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials

SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"
CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"

try: from nexus_config import ORATS_API_KEY
except: ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

def get_workbook():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)

def run_backfill():
    dates_to_fetch = ["2026-03-09", "2026-03-06", "2026-03-05", "2026-03-04"]
    
    wb = get_workbook()
    try:
        ws = wb.worksheet("Historical Data")
        print("Wiping previous flattened historical data from sheets...")
        ws.clear()
        ws.append_row(["Trade Date", "Expiration", "Strike", "Type", "Volume", "Open Interest"])
    except:
        ws = wb.add_worksheet(title="Historical Data", rows=1000, cols=10)
        ws.append_row(["Trade Date", "Expiration", "Strike", "Type", "Volume", "Open Interest"])
        
    for trade_date in dates_to_fetch:
        for ticker in ['SPX', 'SPXW', 'SPY']:
            print(f"Fetching TRUE ORATS HISTORICAL EOD for {trade_date} ({ticker})...")
            url = "https://api.orats.io/datav2/hist/strikes"
            params = {
                'token': ORATS_API_KEY,
                'ticker': ticker,
                'tradeDate': trade_date
            }
            
            try:
                r = requests.get(url, params=params, timeout=30)
                r.raise_for_status()
                data = r.json().get('data', [])
            except Exception as e:
                print(f"❌ ORATS API FAILED on {trade_date} ({ticker}): {e}")
                continue
                
            if not data:
                print(f"⚠️ ORATS Payload Empty for {trade_date} ({ticker}).")
                continue
                
            rows_to_insert = []
            for item in data:
                exp_date_str = item.get('expirDate')
                if not exp_date_str: continue
                
                try:
                    exp_date = datetime.datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                    if exp_date.weekday() != 4: continue # Friday Expire Only
                    
                    strike = float(item.get('strike', 0.0))
                    c_vol = int(item.get('callVolume', 0))
                    c_oi = int(item.get('callOpenInterest', 0))
                    rows_to_insert.append([trade_date, exp_date_str, strike, 'Call', c_vol, c_oi])
                    
                    p_vol = int(item.get('putVolume', 0))
                    p_oi = int(item.get('putOpenInterest', 0))
                    rows_to_insert.append([trade_date, exp_date_str, strike, 'Put', p_vol, p_oi])
                    
                except Exception as e:
                    continue
                    
            if rows_to_insert:
                ws.append_rows(rows_to_insert, value_input_option='USER_ENTERED')
                print(f"✅ Downloaded and appended {len(rows_to_insert)} pure integer rows for {trade_date} ({ticker}).")

if __name__ == "__main__":
    run_backfill()
