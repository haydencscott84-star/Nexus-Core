import asyncio
from supabase_bridge import get_supabase_client
import json

client = get_supabase_client()
if client:
    res = client.table("nexus_profile").select("data").eq("id", "spy_latest").execute()
    if res.data and len(res.data) > 0:
        data = res.data[0]["data"]
        print("Got data!")
        print(f"Keys: {list(data.keys())}")
        if "gex_structure" in data:
            print(f"gex_structure length: {len(data['gex_structure'])}")
    else:
        print("No data found for 'spy_latest'")
else:
    print("No Supabase client")
