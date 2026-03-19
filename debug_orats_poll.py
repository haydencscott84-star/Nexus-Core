
TARGET_FILE = "/root/nexus_spreads.py"

DEBUG_POLL_BLOCK = """    async def poll_orats_greeks(self):
        while True:
            try:
                # DEBUG LOG START
                with open('/tmp/orats_poll_debug.txt', 'a') as f:
                    f.write("Polling ORATS...\\n")
                # DEBUG LOG END

                url = "https://api.orats.io/datav2/live/strikes"
                params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, params=params, timeout=10) as r:
                        # DEBUG LOG STATUS
                        with open('/tmp/orats_poll_debug.txt', 'a') as f:
                            f.write(f"Response Status: {r.status}\\n")

                        if r.status == 200:
                            data = (await r.json()).get('data', [])
                            
                            # DEBUG LOG DATA COUNT
                            with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                f.write(f"Data Items Received: {len(data)}\\n")
                            
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
                                with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                    f.write(f"Map Populated. Keys: {len(temp_map)}\\nExample Key: {list(temp_map.keys())[0]}\\n")
                        else:
                             with open('/tmp/orats_poll_debug.txt', 'a') as f:
                                f.write(f"Failed. Status: {r.status}\\nText: {await r.text()}\\n")

            except Exception as e:
                 with open('/tmp/orats_poll_debug.txt', 'a') as f:
                     f.write(f"ORATS Poll Error: {e}\\n")
            
            await asyncio.sleep(60)
"""

def inject_poll_debug():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Find existing poll_orats_greeks
        start_idx = content.find("async def poll_orats_greeks(self):")
        if start_idx == -1:
            print("Error: poll_orats_greeks not found")
            return
            
        # Find end (next def)
        import re
        all_defs = [m.start() for m in re.finditer(r'\n    def ', content)]
        future_defs = [d for d in all_defs if d > start_idx]
        if future_defs:
            end_idx = future_defs[0]
        else:
            end_idx = len(content)

        old_block = content[start_idx:end_idx]
        
        # Replace
        new_content = content.replace(old_block, DEBUG_POLL_BLOCK)
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Poll Debug Injected.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inject_poll_debug()
