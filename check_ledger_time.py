import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res_spx = client.table("nexus_profile").select("data").eq("id", "spx_flow_ledger").execute()
res_spy = client.table("nexus_profile").select("data").eq("id", "spy_flow_ledger").execute()

try:
    if res_spx.data and isinstance(res_spx.data[0]['data'], list) and len(res_spx.data[0]['data']) > 0:
        spx_date = res_spx.data[0]['data'][-1].get('Date') or res_spx.data[0]['data'][0].get('Date')
        print("SPX Ledger Date:", spx_date)
        print("SPX Raw Length:", len(res_spx.data[0]['data']))
    else:
        print("SPX Ledger Date: None (Empty/Missing)")
except Exception as e:
    print("SPX Error:", e)

try:
    if res_spy.data and isinstance(res_spy.data[0]['data'], list) and len(res_spy.data[0]['data']) > 0:
        spy_date = res_spy.data[0]['data'][-1].get('Date') or res_spy.data[0]['data'][0].get('Date')
        print("SPY Ledger Date:", spy_date)
        print("SPY Raw Length:", len(res_spy.data[0]['data']))
    else:
        print("SPY Ledger Date: None (Empty/Missing)")
except Exception as e:
    print("SPY Error:", e)
