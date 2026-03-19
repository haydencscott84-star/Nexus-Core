import requests
import os
from dotenv import load_dotenv

load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

endpoint = f"{url}/rest/v1/nexus_profile?select=id"
headers = {"apikey": key, "Authorization": f"Bearer {key}"}

resp = requests.get(endpoint, headers=headers)
if resp.status_code == 200:
    for item in resp.json():
        print(item.get("id"))
else:
    print("Error:", resp.text)
