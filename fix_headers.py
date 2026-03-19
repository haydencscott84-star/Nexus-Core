import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    wb = client.open_by_key(SHEET_ID)
    ws = wb.worksheet("Historical Data")

    print(f"Total Rows Before: {ws.row_count}")
    vals = ws.get_all_values()
    
    clean_vals = []
    
    for row in vals:
        if not any(cell.strip() for cell in row): continue
        if row[0].strip().lower() == 'trade date': continue
        clean_vals.append(row)

    print(f"Total Data Rows: {len(clean_vals)}")
    
    print("Clearing sheet...")
    ws.clear()
    time.sleep(2)
    
    headers = ["Trade Date", "Expiration", "Strike", "Type", "Volume", "Open Interest"]
    ws.append_row(headers)
    
    if clean_vals:
        for i in range(0, len(clean_vals), 5000):
            chunk = clean_vals[i:i+5000]
            print(f"Restoring chunk {i} to {i+len(chunk)}...")
            ws.append_rows(chunk)

    print("Header Fix Done!")

except Exception as e:
    print(f"Error: {e}")
