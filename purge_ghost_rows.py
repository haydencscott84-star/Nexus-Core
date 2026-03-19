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

    total_rows = ws.row_count
    vals = ws.get_all_values()
    data_rows = len(vals)
    
    print(f"Total rows: {total_rows}")
    print(f"Data rows: {data_rows}")
    
    # Let's delete the ghost extra rows to force the Pivot Table array to clean up.
    if total_rows > data_rows:
        num_to_delete = total_rows - data_rows
        print(f"Found {num_to_delete} ghost empty rows! Deleting from bottom...")
        
        # We delete starting from the row after the last data row, to the end of the sheet
        start_del = data_rows + 1
        
        # gspread uses 1-indexed operations.
        # But wait, resize is faster.
        print("Resizing sheet to match data bounds exactly...")
        ws.resize(rows=data_rows)
        print("Resize complete!")
    else:
        print("No ghost rows found.")

except Exception as e:
    print(f"Error: {e}")
