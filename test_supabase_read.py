import os
import json
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv("/Users/haydenscott/Desktop/Local Scripts/.env")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res = client.table("nexus_profile").select("data").eq("id", "broad_market").execute()
if res.data and len(res.data) > 0:
    data = res.data[0]["data"]
    print("KEYS IN SUPABASE:")
    prices = data.get("prices", {})
    print(list(prices.keys()))
    for k, v in prices.items():
        print(f"{k}: {v.get('curr')}")
else:
    print("NO DATA")
