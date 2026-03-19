import json
import urllib.request
from oauth2client.service_account import ServiceAccountCredentials

CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"

def fix_pivot_table_urllib():
    print("Connecting to Google Sheets via pure urllib...")
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    
    # Get the raw access token
    access_token = creds.get_access_token().access_token
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    print("Fetching spreadsheet metadata...")
    url_get = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?includeGridData=false'
    req = urllib.request.Request(url_get, headers=headers)
    
    with urllib.request.urlopen(req) as response:
        raw_data = json.loads(response.read().decode())

    hist_sheet_id = None
    pivot_sheet_id = None
    for s in raw_data['sheets']:
        title = s['properties']['title']
        if title == 'Historical Data':
            hist_sheet_id = s['properties']['sheetId']
        if title == 'Pivot Table 3':
            pivot_sheet_id = s['properties']['sheetId']

    if hist_sheet_id is None or pivot_sheet_id is None:
        print("Could not find required sheets (Historical Data or Pivot Table 3).")
        return

    print("Locating the Pivot Table component...")
    url_pivot = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?ranges=Pivot%20Table%203&fields=sheets.data.rowData.values.pivotTable,sheets.data.rowData.values.effectiveValue,sheets.properties.sheetId'
    
    req_pivot = urllib.request.Request(url_pivot, headers=headers)
    with urllib.request.urlopen(req_pivot) as response:
        pivot_data = json.loads(response.read().decode())

    sheet = pivot_data['sheets'][0]
    found = False
    
    for r_idx, row in enumerate(sheet.get('data', [{}])[0].get('rowData', [])):
        for c_idx, cell in enumerate(row.get('values', [])):
            if 'pivotTable' in cell:
                print(f"Pivot Table found at Row {r_idx + 1}, Col {c_idx + 1}! Updating data source...")
                pt = cell['pivotTable']
                
                # Force the source range to align with A:F of Historical Data
                pt['source'] = {
                    'sheetId': hist_sheet_id,
                    'startRowIndex': 0,
                    'startColumnIndex': 0,
                    'endColumnIndex': 6 
                }
                
                # Send batch update
                update_req = {
                    "updateCells": {
                        "rows": [
                            {
                                "values": [
                                    {
                                        "pivotTable": pt
                                    }
                                ]
                            }
                        ],
                        "start": {
                            "sheetId": pivot_sheet_id,
                            "rowIndex": r_idx,
                            "columnIndex": c_idx
                        },
                        "fields": "pivotTable"
                    }
                }
                
                url_update = f'https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}:batchUpdate'
                payload = json.dumps({"requests": [update_req]}).encode('utf-8')
                req_update = urllib.request.Request(url_update, data=payload, headers=headers, method='POST')
                
                with urllib.request.urlopen(req_update) as response:
                    res_body = response.read().decode()
                    if response.status == 200:
                        print("Pivot table successfully updated to target new data!")
                    else:
                        print(f"Error updating: {res_body}")
                found = True
                break
        if found:
            break

    if not found:
        print("Could not find a Pivot Table inside 'Pivot Table 3'.")

if __name__ == "__main__":
    try:
        fix_pivot_table_urllib()
    except Exception as e:
        print(f"Fatal error: {e}")
