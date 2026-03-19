import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import datetime
import time

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

try:
    from nexus_config import ORATS_API_KEY
except:
    ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)
ws = wb.worksheet("Historical Data")

def fetch_orats_for_date(trade_date):
    url = "https://api.orats.io/datav2/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY', 'tradeDate': trade_date}
    r = requests.get(url, params=params, timeout=30)
    if r.status_code != 200:
        print(f"Failed to fetch {trade_date}: {r.status_code}")
        return []
    data = r.json().get('data', [])
    rows = []
    for item in data:
        exp_date_str = item.get('expirDate')
        if not exp_date_str: continue
        try:
            exp_date = datetime.datetime.strptime(exp_date_str, "%Y-%m-%d").date()
            if exp_date.weekday() != 4: continue # Friday Expire Only
            
            strike = float(item.get('strike', 0.0))
            c_vol = int(item.get('callVolume', 0))
            c_oi = int(item.get('callOpenInterest', 0))
            if c_oi > 0 or c_vol > 0:
                rows.append([trade_date, exp_date_str, strike, 'Call', c_vol, c_oi])
            
            p_vol = int(item.get('putVolume', 0))
            p_oi = int(item.get('putOpenInterest', 0))
            if p_oi > 0 or p_vol > 0:
                rows.append([trade_date, exp_date_str, strike, 'Put', p_vol, p_oi])
        except Exception as e:
            pass
    return rows

print("Clearing sheet...")
ws.clear()
headers = ["Trade Date", "Expiration", "Strike", "Type", "Volume", "Open Interest"]
ws.append_row(headers)

dates_to_fetch = ["2026-03-10", "2026-03-11", "2026-03-12", "2026-03-13"]
all_rows = []
for d in dates_to_fetch:
    print(f"Fetching {d}...")
    rows = fetch_orats_for_date(d)
    print(f"Got {len(rows)} rows for {d}")
    all_rows.extend(rows)
    time.sleep(1)

print(f"Uploading {len(all_rows)} rows total...")
if all_rows:
    for i in range(0, len(all_rows), 5000):
        chunk = all_rows[i:i+5000]
        print(f"Appending chunk {i} to {i+len(chunk)}...")
        ws.append_rows(chunk)

print("Done!")
