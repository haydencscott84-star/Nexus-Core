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
df_spx = df[df['Strike'] >= 3000].copy()
test_strike = df_spx[(df_spx['Strike'] == 6000) & (df_spx['Type'] == 'Call') & (df_spx['Expiration'] == '2026-03-20')]
print("6000 Call 3/20 Data across Dates (SPX):")
print(test_strike[['Trade Date', 'Expiration', 'Volume', 'Open Interest']])
