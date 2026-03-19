import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import glob
import datetime

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    wb = client.open_by_key(SHEET_ID)
    ws = wb.worksheet("Historical Data")
    
    print("Clearing sheet...")
    ws.clear()
    headers = ["Trade Date", "Expiration", "Strike", "Type", "Volume", "Open Interest"]
    ws.append_row(headers)

    # 16:-- matches end of day (market close).
    target_dates = {
        "2026-03-10": "spx_snapshot_2026-03-10_16*.csv",
        "2026-03-11": "spx_snapshot_2026-03-11_16*.csv",
        "2026-03-12": "spx_snapshot_2026-03-12_16*.csv",
        "2026-03-13": "spx_snapshot_2026-03-13_16*.csv"
    }

    all_rows = []
    
    for t_date, pattern in target_dates.items():
        files = glob.glob(f"/root/snapshots/{pattern}")
        if not files:
            print(f"Skipping {t_date}: No snapshots matching {pattern}")
            continue
            
        files.sort()
        target_file = files[-1]
        print(f"Parsing {target_file} for {t_date}...")
        
        try:
            df = pd.read_csv(target_file)
            
            # Nexus snapshot headers typically: sym,exp,dte,stk,type,bid,ask...
            # We map stk->Strike, exp->Expiration, vol/oi might be missing if it's just flow.
            # Wait, nexus_sweeps or spx_profiler generates these CSVs. 
            # If they don't have OI, we cannot reconstruct OI.
            print("Columns found:", list(df.columns))
            
            needed_cols = ['exp', 'stk', 'type', 'vol']
            if not all(c.lower() in [col.lower() for col in df.columns] for c in needed_cols):
                 print(f"CSV {target_file} missing columns!")
                 continue
                 
            # Convert to dictionary for easy case-insensitive access
            cols = {c.lower(): c for c in df.columns}
            
            for index, row in df.iterrows():
                 try:
                     exp_str = str(row[cols['exp']])
                     exp_date = datetime.datetime.strptime(exp_str, "%Y-%m-%d").date()
                     if exp_date.weekday() != 4: continue # Friday Expire Only
                     
                     strike = float(row[cols['stk']])
                     typ_str = str(row[cols['type']]).upper()
                     typ = "Call" if typ_str.startswith("C") else "Put"
                     
                     vol = 0
                     if 'vol' in cols: vol = int(float(row[cols['vol']]))
                     
                     oi = 0
                     if 'oi' in cols: oi = int(float(row[cols['oi']]))
                     
                     if vol > 0 or oi > 0:
                         all_rows.append([t_date, exp_str, strike, typ, vol, oi])
                 except Exception as e:
                     pass
        except Exception as e:
             print(f"Error parsing {target_file}: {e}")

    print(f"Uploading {len(all_rows)} rows total...")
    if all_rows:
        for i in range(0, len(all_rows), 5000):
            chunk = all_rows[i:i+5000]
            print(f"Appending chunk {i} to {i+len(chunk)}...")
            ws.append_rows(chunk)

    print("Historical backfill complete.")
except Exception as e:
    print(f"Fatal Error: {e}")
