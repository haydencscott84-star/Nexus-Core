import os
from supabase import create_client
from dotenv import load_dotenv

load_dotenv('/Users/haydenscott/Desktop/Local Scripts/.env')
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
client = create_client(url, key)

res = client.table("nexus_profile").select("data").eq("id", "broad_market").execute()
print(f"Rows: {len(res.data)}")
if res.data:
    print(res.data[0]["data"].keys())
else:
    print("NO DATA FOUND FOR broad_market")
