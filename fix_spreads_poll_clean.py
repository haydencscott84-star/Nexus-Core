
TARGET_FILE = "/root/nexus_spreads.py"

CLEAN_METHOD = """    async def poll_orats_greeks(self):
        while True:
            try:
                url = "https://api.orats.io/datav2/live/strikes"
                params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, params=params, timeout=10) as r:
                        if r.status == 200:
                            data = (await r.json()).get('data', [])
                            temp_map = {}
                            for i in data:
                                try:
                                    k = f"{i['expirDate']}|{float(i['strike']):.1f}"
                                    d = float(i.get('delta', 0))
                                    v = float(i.get('impliedVolatility', i.get('iv', 0)))
                                    temp_map[k] = {'delta': d, 'iv': v}
                                except: pass
                            
                            if temp_map:
                                self.orats_map = temp_map
            except Exception as e:
                 # self.log_msg(f"ORATS Poll Error: {e}")
                 pass
            
            await asyncio.sleep(60)

"""

def fix_overwrite_clean():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        start_idx = -1
        end_idx = -1
        
        for i, line in enumerate(lines):
            if "async def poll_orats_greeks(self):" in line:
                start_idx = i
            if start_idx != -1 and "def populate_chain" in line:
                end_idx = i
                break
        
        if start_idx != -1 and end_idx != -1:
            print(f"Replacing lines {start_idx} to {end_idx} with CLEAN version...")
            new_lines = lines[:start_idx] + [CLEAN_METHOD] + lines[end_idx:]
            
            with open(TARGET_FILE, 'w') as f:
                f.writelines(new_lines)
            print("Clean Method Overwrite Complete.")
        else:
            print(f"Indices not found. Start: {start_idx}, End: {end_idx}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_overwrite_clean()
