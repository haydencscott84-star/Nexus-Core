import json, gspread
from oauth2client.service_account import ServiceAccountCredentials

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('/root/tribal-flux-476216-c0-70e4f946eb77.json', scope)
client = gspread.authorize(creds)
wb = client.open_by_key('1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg')
ws = wb.worksheet('Historical Data')
ws.insert_row(['Trade Date', 'Expiration', 'Strike', 'Type', 'Volume', 'Open Interest'], 1)
print('Headers successfully injected.')
