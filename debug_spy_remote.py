import asyncio
from supabase_bridge import get_supabase_client
import json

client = get_supabase_client()
if client:
    res = client.table("nexus_profile").select("data").eq("id", "spy_latest").execute()
    if res.data and len(res.data) > 0:
        data = res.data[0]["data"]
        
        print(f"Header Magnet: {data.get('magnet')}")
        print(f"Header Zero: {data.get('zero_gamma')}")
        
        if "gex_structure" in data and len(data['gex_structure']) > 0:
            first = data['gex_structure'][0]
            print(f"Struct 0 Vol POC: {first.get('volume_poc_strike')}")
            print(f"Struct 0 Flip: {first.get('gex_flip_point')}")
