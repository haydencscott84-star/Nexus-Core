import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = '1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg'

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)

for sheet_name in ["5-Day Flow Ledger", "SPY 5-Day Flow Ledger"]:
    try:
        ws = wb.worksheet(sheet_name)
        sheet_id = ws.id
        print(f"\n--- Cleaning {sheet_name} (ID: {sheet_id}) ---")
        deleted = 0
        while True:
            try:
                clear_req = {"deleteConditionalFormatRule": {"index": 0, "sheetId": sheet_id}}
                wb.batch_update({"requests": [clear_req]})
                deleted += 1
                print(f"Deleted rule {deleted}")
            except Exception as e:
                # We expect an APIError when no rules are left
                break
        print(f"Total deleted for {sheet_name}: {deleted}")
    except Exception as e:
        print(e)
