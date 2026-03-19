import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    wb = client.open_by_key(SHEET_ID)
    
    print("--- Worksheets ---")
    for ws in wb.worksheets():
        print(f"Sheet: {ws.title}, Rows: {ws.row_count}")
        
    print("\n--- Historical Data Check ---")
    hi_ws = wb.worksheet("Historical Data")
    vals = hi_ws.get_all_values()
    if len(vals) > 1:
        dates = [r[0] for r in vals[1:]]
        unique_dates = set(dates)
        print(f"Total Rows: {len(vals)}")
        print(f"Unique Dates: {unique_dates}")
        print(f"First 3 rows: {vals[0:3]}")
    else:
        print("Historical Data is empty or only has headers.")
except Exception as e:
    print(f"Error: {e}")
