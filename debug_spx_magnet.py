import asyncio
from supabase_bridge import get_supabase_client
import json

client = get_supabase_client()
res = client.table("nexus_profile").select("data").eq("id", "spx_latest").execute()
if res.data and len(res.data) > 0:
    prof_data = res.data[0]["data"]
    print(f"SPX Major Levels: {prof_data.get('major_levels', {})}")
else:
    print("No SPX data found")
