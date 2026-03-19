
TARGET_FILE = "/root/nexus_spreads.py"

clean_poll_func = """    async def poll_orats_greeks(self):
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
            await asyncio.sleep(60)"""

def fix_clean():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        # We will rewrite the file, but we need to identify the start/end of the bad function
        # and replace it with clean_poll_func
        
        new_lines = []
        skip = False
        injected = False
        
        for line in lines:
            stripped = line.strip()
            
            # Start of function
            if "async def poll_orats_greeks(self):" in line:
                skip = True
                # Add check to ensure we don't inject multiple times if run multiple times
                if not injected:
                    new_lines.append(clean_poll_func + "\n")
                    injected = True
                continue
            
            # End of function detection
            # We assume the next function starts with '    def' (4 spaces)
            if skip:
                if line.startswith("    def ") and "poll_orats_greeks" not in line:
                    skip = False
                    new_lines.append(line)
                # Else: we are skipping the bad body lines
                continue
            
            if not skip:
                new_lines.append(line)
                
        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Clean fix applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_clean()
