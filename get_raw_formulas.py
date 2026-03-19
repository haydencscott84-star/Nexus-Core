import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = '1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg'

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)
ws = wb.worksheet("5-Day Flow Ledger")

# value_render_option="FORMULA" to see the literal injected string
res = ws.get("I1:L4", value_render_option="FORMULA")
for row in res:
    print(row)
