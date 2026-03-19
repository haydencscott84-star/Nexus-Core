import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()
ts_token = os.environ.get("TS_ACCESS_TOKEN")

url = "https://api.tradestation.com/v3/marketdata/quotes/MESH26,MESM26,@MES,@ES"
headers = {"Authorization": f"Bearer {ts_token}"}

resp = requests.get(url, headers=headers)
print(resp.status_code)
if resp.status_code == 200:
    data = resp.json().get('Quotes', [])
    for q in data:
        print(f"{q.get('Symbol')}: Last={q.get('Last', 'N/A')}, Vol={q.get('TotalVolume', 'N/A')}")
else:
    print(resp.text)
