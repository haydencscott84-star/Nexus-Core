import asyncio
from supabase_bridge import get_supabase_client
import collections

async def test_fetch():
    client = get_supabase_client()
    res = await asyncio.to_thread(lambda: client.table("nexus_profile").select("data").eq("id", "market_regime").execute())
    if len(res.data) > 0 and 'data' in res.data[0]:
        r_data = res.data[0]['data']
        headers = r_data.get('headers', [])
        print("Headers:", headers)
        dupes = [item for item, count in collections.Counter(headers).items() if count > 1]
        print("Duplicates:", dupes)
    else:
        print("No market_regime data.")

asyncio.run(test_fetch())
