import asyncio
from supabase_bridge import get_supabase_client
import pandas as pd

async def test_fetch():
    client = get_supabase_client()
    res_spx = await asyncio.to_thread(lambda: client.table("nexus_profile").select("data").eq("id", "spx_flow_ledger").execute())
    if len(res_spx.data) > 0 and 'data' in res_spx.data[0]:
        s_data = res_spx.data[0]['data']
        df_spx_vol = pd.DataFrame(s_data.get('top_vol', []))
        print(f"Columns in Top Vol: {df_spx_vol.columns.tolist()}")
        print(df_spx_vol.head(1).to_dict('records'))
    else:
        print("No data.")

asyncio.run(test_fetch())
