import asyncio
from supabase_bridge import get_supabase_client
import json

async def test_fetch():
    client = get_supabase_client()
    try:
        res = getattr(client.table("nexus_profile").select("*").eq('id', 'spy_flow_ledger').execute(), 'data', [])
        print("Data top_oi row 0:")
        if res and len(res) > 0 and 'data' in res[0] and 'top_oi' in res[0]['data'] and len(res[0]['data']['top_oi']) > 0:
            print(json.dumps(res[0]['data']['top_oi'][0], indent=2))
        else:
            print("No data found")
    except Exception as e:
        print(f"Error: {e}")
asyncio.run(test_fetch())
