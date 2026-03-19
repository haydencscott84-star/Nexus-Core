import asyncio
from supabase_bridge import get_supabase_client

async def test_fetch():
    client = get_supabase_client()
    try:
        response = await asyncio.to_thread(
            lambda: client.table("nexus_profile").select("*").execute()
        )
        for row in response.data:
            print(f"✅ Found row ID: {row['id']}")
            if row['id'] in ['market_regime', 'spx_flow_ledger', 'spy_flow_ledger']:
                print(f"   -> Data size: {len(str(row.get('data', '')))} chars")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
