import asyncio
from supabase_bridge import get_supabase_client
import json

client = get_supabase_client()
res = client.table("nexus_profile").select("data").eq("id", "spy_latest").execute()
prof_data = res.data[0]["data"]

raw_mag = prof_data.get('magnet', 0)
if isinstance(raw_mag, dict): magnet = raw_mag.get('strike', 0)
else: magnet = float(raw_mag) if raw_mag else 0
    
raw_zero = prof_data.get('zero_gamma', 0)
if isinstance(raw_zero, dict): zero_gamma = raw_zero.get('strike', 0)
else: zero_gamma = float(raw_zero) if raw_zero else 0

print(f"Magnet Result: {magnet}")
print(f"Zero Gamma Result: {zero_gamma}")
