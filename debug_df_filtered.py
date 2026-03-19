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
print(f"Initial length: {len(df)}")

date_col = 'Trade Date'
strike_col = 'Strike'
type_col = 'Type'
oi_col = 'Open Interest'
vol_col = 'Volume'
exp_col = 'Expiration'

print("Applying types...")
df[date_col] = pd.to_datetime(df[date_col], format='mixed', errors='coerce')
df[strike_col] = pd.to_numeric(df[strike_col], errors='coerce')
df[oi_col] = pd.to_numeric(df[oi_col], errors='coerce').fillna(0)
df[vol_col] = pd.to_numeric(df[vol_col], errors='coerce').fillna(0)

print(f"Length before dropna: {len(df)}")
df = df.dropna(subset=[date_col, strike_col])
print(f"Length after dropna: {len(df)}")

unique_dates = sorted(df[date_col].dt.date.unique())
print(f"Unique dates: {unique_dates}")

last_5_days = unique_dates[-5:]
df_filtered = df[df[date_col].dt.date.isin(last_5_days)].copy()

daily_aggregated = df_filtered.groupby([date_col, strike_col, type_col, exp_col], as_index=False).agg({vol_col: 'sum', oi_col: 'sum'})

print(f"Daily Aggregated Groups: {len(daily_aggregated)}")

top_vol_check_size = 0
for (strike, opt_type), group in daily_aggregated.groupby([strike_col, type_col]):
    strike_daily = group.groupby(date_col).agg({vol_col: 'sum', oi_col: 'sum'}).reset_index().sort_values(by=date_col)
    if strike_daily.empty: continue
    top_vol_check_size += 1
    
print(f"Valid Results Count for final output loops: {top_vol_check_size}")
