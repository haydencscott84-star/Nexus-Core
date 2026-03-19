import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

try:
    print("Authenticating...")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    wb = client.open_by_key(SHEET_ID)
    ws = wb.worksheet("Historical Data")

    print("Fetching sheet data...")
    vals = ws.get_all_values()
    
    if len(vals) < 2:
        print("Not enough data.")
        exit()

    headers = vals[0]
    data = vals[1:]
    
    print("Formatting numerical columns...")
    formatted_data = []
    
    for row in data:
        # Expected: Trade Date, Expiration, Strike, Type, Volume, Open Interest
        if len(row) < 6: continue
        
        t_date = row[0]
        exp = row[1]
        strike = float(row[2]) if row[2] else 0.0
        typ = row[3]
        vol = int(row[4]) if row[4] else 0
        oi = int(row[5]) if row[5] else 0
        
        formatted_data.append([t_date, exp, strike, typ, vol, oi])

    print("Clearing sheet...")
    ws.clear()
    time.sleep(2)
    
    print("Re-uploading with USER_ENTERED formatting...")
    ws.append_row(headers)
    
    for i in range(0, len(formatted_data), 5000):
        chunk = formatted_data[i:i+5000]
        print(f"Uploading chunk {i} to {i+len(chunk)}...")
        ws.append_rows(chunk, value_input_option='USER_ENTERED')
        
    print("Data type formatting complete! Pivot table should now calculate.")

except Exception as e:
    print(f"Error: {e}")
