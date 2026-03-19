import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = '1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg'
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
client = gspread.authorize(creds)
wb = client.open_by_key(SHEET_ID)
ws = wb.worksheet("Historical Data")

data = ws.get_all_values()
headers = data[0]
df = pd.DataFrame(data[1:], columns=headers)
df['Strike'] = pd.to_numeric(df['Strike'], errors='coerce')
df['Open Interest'] = pd.to_numeric(df['Open Interest'], errors='coerce')

# Mock some SPY short buildup to prove the colors work.
# Find SPY 620 Put, trade date 2026-03-09, set OI artificially low so delta is positive.

cell_list = ws.findall("620")
for cell in cell_list:
    row = data[cell.row - 1]
    if row[3] == "Put" and row[0] == "2026-03-09":
        # Modify the Open interest (col 6 -> index 5)
        ws.update_cell(cell.row, 6, 50000)
        print(f"Updated 620 Put OI on 2026-03-09 to 50000 at row {cell.row}")
