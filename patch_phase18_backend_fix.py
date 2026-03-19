
# PATCH PHASE 18 BACKEND FIX
# Target: ts_nexus.py
# Goal: Include 'price' (SPY Price) in GET_CHAIN response so UI has it for calculations.

FILE = "ts_nexus.py"

GET_CHAIN_FIX = r'''
                elif cmd == "GET_CHAIN":
                    ticker = msg.get("ticker", "SPY")
                    strike = msg.get("strike")
                    width = msg.get("width")
                    type_ = msg.get("type", "PUT")
                    
                    # Parallel Fetch: Chain + IVR
                    chain_task = self.fetch_option_chain(ticker, strike, width, type_)
                    ivr_task = self.fetch_orats_ivr(ticker)
                    
                    data, (iv, ivr) = await asyncio.gather(chain_task, ivr_task)

                    # Ensure we have price
                    price = self.latest_spy_price
                    if price <= 0:
                        # Try simple fetch if missing
                        try:
                             url = f"{self.TS.BASE_URL}/marketdata/quotes/{ticker}"
                             headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
                             # Helper synchronous request in async flow (ok for quick patch)
                             import requests
                             r = requests.get(url, headers=headers)
                             if r.status_code == 200:
                                 q = r.json().get("Quotes", [])
                                 if q: price = float(q[0].get("Last", 0))
                                 self.latest_spy_price = price
                        except: pass
                    
                    # Attach Price to response
                    await self.exec_sock.send_json({"status": "ok", "data": data, "iv": iv, "ivr": ivr, "price": price})
                    continue
'''

def patch_backend_fix():
    with open(FILE, 'r') as f: content = f.read()
    
    # Replace the existing GET_CHAIN block (which we just patched).
    # We can match on the inner contents or the structure.
    # The previous patch used: elif cmd == "GET_CHAIN": ... continue
    
    import re
    pattern = r'(elif cmd == "GET_CHAIN":.*?continue)'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        content = content.replace(match.group(1), GET_CHAIN_FIX.strip())
        print("Updated GET_CHAIN to include Price.")
        with open(FILE, 'w') as f: f.write(content)
    else:
        print("Could not find GET_CHAIN block.")

if __name__ == "__main__":
    patch_backend_fix()
