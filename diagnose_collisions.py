
import aiohttp
import asyncio
import os

ORATS_API_KEY = os.getenv("ORATS_API_KEY", os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

async def check_collisions():
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    
    print("Fetching Data...")
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, params=params) as r:
            data = (await r.json()).get('data', [])
            
    temp_map = {}
    collisions = 0
    bad_overwrites = 0
    
    print(f"Processing {len(data)} rows...")
    
    for i in data:
        try:
            # Replicate nexus_spreads.py logic EXACTLY
            k = f"{i['expirDate']}|{float(i['strike']):.1f}"
            
            # Using smvVol logic
            v = float(i.get('smvVol', i.get('impliedVolatility', i.get('iv', 0))))
            
            if k in temp_map:
                collisions += 1
                prev_v = temp_map[k]['iv']
                if prev_v > 0 and v == 0:
                    bad_overwrites += 1
                    print(f"CRITICAL OVERWRITE: Key {k} had IV {prev_v}, replaced by {v} (0.0).")
                    print(f"   -> Prev Row vs Curr Row logic collision.")
                elif prev_v == 0 and v > 0:
                    print(f"Good Overwrite: Key {k} had 0.0, replaced by {v}.")
                
            temp_map[k] = {'iv': v}
            
        except Exception as e:
            print(f"Error: {e}")
            
    print("-" * 40)
    print(f"Total Collisions: {collisions}")
    print(f"Bad Overwrites (Non-Zero -> Zero): {bad_overwrites}")
    
    # Check specifically for 675
    target_k = f"2026-01-30|675.0" # Example
    # Check any 675 keys
    print("\nChecking 675 Keys in Final Map:")
    found_675 = [k for k in temp_map.keys() if "|675.0" in k]
    for k in found_675[:5]:
        print(f"Key {k}: IV={temp_map[k]['iv']}")

if __name__ == "__main__":
    asyncio.run(check_collisions())
