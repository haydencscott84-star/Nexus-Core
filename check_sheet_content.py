import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    wb = client.open_by_key(SHEET_ID)
    ws = wb.worksheet("Historical Data")

    print(f"Total Rows Reported: {ws.row_count}")
    vals = ws.get_all_values()
    
    print(f"Total Rows with Data: {len(vals)}")
    print(f"Headers: {vals[0] if vals else 'None'}")
    
    # Check sample rows
    if len(vals) > 1:
        print(f"Row 2: {vals[1]}")
    if len(vals) > 5000:
        print(f"Row 5000: {vals[4999]}")

except Exception as e:
    print(f"Error: {e}")
