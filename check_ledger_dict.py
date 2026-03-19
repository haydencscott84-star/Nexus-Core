import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res_spx = client.table("nexus_profile").select("data").eq("id", "spx_flow_ledger").execute()
res_spy = client.table("nexus_profile").select("data").eq("id", "spy_flow_ledger").execute()

def check_ledger(res, name):
    try:
        if res.data and len(res.data) > 0:
            data = res.data[0]['data']
            if isinstance(data, dict):
                top_vol = data.get('top_vol', [])
                top_oi = data.get('top_oi', [])
                print(f"{name} Ledger found. Top Vol Length: {len(top_vol)}, Top OI Length: {len(top_oi)}")
                
                if len(top_vol) > 0:
                    print(f"Sample Top Vol Keys: {list(top_vol[0].keys())}")
                print(f"**LAST UPDATED**: {data.get('last_updated', 'MISSING!')}")
            else:
                print(f"{name} Ledger: Unexpected data type: {type(data)}")
        else:
            print(f"{name} Ledger: Missing or empty Supabase table")
    except Exception as e:
        print(f"{name} Error processing: {e}")

check_ledger(res_spx, "SPX")
check_ledger(res_spy, "SPY")
