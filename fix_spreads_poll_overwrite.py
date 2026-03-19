
TARGET_FILE = "/root/nexus_spreads.py"

CLEAN_METHOD = """    async def poll_orats_greeks(self):
        while True:
            try:
                # DEBUG LOG START
                try:
                    with open('/tmp/orats_poll_debug.txt', 'a') as f:
                        f.write(f"Polling ORATS... {datetime.datetime.now()}\\n")
                except: pass
                # DEBUG LOG END

                url = "https://api.orats.io/datav2/live/strikes"
                params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, params=params, timeout=10) as r:
                        # DEBUG LOG STATUS
                        try:
                            with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                f.write(f"Response Status: {r.status}\\n")
                        except: pass

                        if r.status == 200:
                            data = (await r.json()).get('data', [])
                            
                            # DEBUG LOG DATA COUNT
                            try:
                                with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                    f.write(f"Data Items Received: {len(data)}\\n")
                            except: pass
                            
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
                                try:
                                    with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                        f.write(f"Map Populated. Keys: {len(temp_map)}\\nExample Key: {list(temp_map.keys())[0]}\\n")
                                except: pass
                        else:
                             try:
                                 txt = await r.text()
                                 with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                    f.write(f"Failed. Status: {r.status}\\nText: {txt}\\n")
                             except: pass

            except Exception as e:
                 try:
                     with open('/tmp/orats_poll_debug.txt', 'a') as f:
                         f.write(f"ORATS Poll Error: {e}\\n")
                 except: pass
            
            await asyncio.sleep(60)

"""

def fix_overwrite():
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
            print(f"Replacing lines {start_idx} to {end_idx}...")
            new_lines = lines[:start_idx] + [CLEAN_METHOD] + lines[end_idx:]
            
            with open(TARGET_FILE, 'w') as f:
                f.writelines(new_lines)
            print("Method Overwrite Complete.")
        else:
            print(f"Indices not found. Start: {start_idx}, End: {end_idx}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_overwrite()
