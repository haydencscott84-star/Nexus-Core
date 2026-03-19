from supabase_bridge import get_supabase_client
import json

client = get_supabase_client()
if client:
    res = client.table("nexus_profile").select("id, data").in_("id", ["spx_flow_ledger", "spy_flow_ledger"]).execute()
    for row in res.data:
        ledger_id = row['id']
        data = row['data']
        
        top_vol = data.get('top_vol', [])
        
        print(f"--- {ledger_id} ---")
        if 'timestamp' in data:
            print(f"Timestamp: {data['timestamp']}")
        else:
            print(f"Timestamp: Not found at root")
        
        if top_vol and len(top_vol) > 0:
            first = top_vol[0]
            print(f"First row keys: {list(first.keys())}")
            print(f"First row date/time approx: {first.get('Date', 'No Date')} | Expiry: {first.get('Top Expiration', 'No Expiry')}")
        else:
            print("No top_vol records found")
else:
    print("Could not get supabase client")
