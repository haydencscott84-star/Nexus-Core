
# PATCH PHASE 17 BACKEND
# 1. Add ORATS_API_KEY to nexus_config.py
# 2. Add fetch_orats_ivr to ts_nexus.py
# 3. Update GET_CHAIN in ts_nexus.py to use it.

import os

CONFIG_FILE = "nexus_config.py"
TS_FILE = "ts_nexus.py"

ORATS_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

def patch_config():
    with open(CONFIG_FILE, 'r') as f: content = f.read()
    if "ORATS_API_KEY" not in content:
        with open(CONFIG_FILE, 'a') as f:
            f.write(f'\nORATS_API_KEY = "{ORATS_KEY}"\n')
        print("Updated nexus_config.py")
    else:
        print("nexus_config.py has key.")

IVR_METHOD = r'''
    async def fetch_orats_ivr(self, ticker):
        """Fetches IV (30d) and IV Rank (1y Percentile) from ORATS."""
        try:
            from nexus_config import ORATS_API_KEY
            if not ORATS_API_KEY: return 0.0, 0.0
            
            url = "https://api.orats.io/datav2/cores"
            params = {"token": ORATS_API_KEY, "ticker": ticker}
            
            # Use requests in thread to avoid blocking
            import requests
            r = await asyncio.to_thread(requests.get, url, params=params)
            
            if r.status_code == 200:
                d = r.json()
                data = d.get("data", [])
                if data:
                    core = data[0]
                    iv = float(core.get('iv30d', 0))
                    ivr = float(core.get('ivPctile1y', 0))
                    self.log_msg(f"ORATS: {ticker} IV={iv}% IVR={ivr}")
                    return iv, ivr
            return 0.0, 0.0
            
        except Exception as e:
            self.log_msg(f"ORATS Error: {e}")
            return 0.0, 0.0
'''

GET_CHAIN_BLOCK = r'''
                elif cmd == "GET_CHAIN":
                    ticker = msg.get("ticker", "SPY")
                    strike = msg.get("strike")
                    width = msg.get("width")
                    type_ = msg.get("type", "PUT")
                    
                    # Parallel Fetch: Chain + IVR
                    chain_task = self.fetch_option_chain(ticker, strike, width, type_)
                    ivr_task = self.fetch_orats_ivr(ticker)
                    
                    data, (iv, ivr) = await asyncio.gather(chain_task, ivr_task)
                    
                    # Attach IV data to response
                    # Standard response: {"status": "ok", "data": [...], "iv": iv, "ivr": ivr}
                    await self.exec_sock.send_json({"status": "ok", "data": data, "iv": iv, "ivr": ivr})
                    continue
'''

def patch_ts_nexus():
    with open(TS_FILE, 'r') as f: content = f.read()
    
    # 1. Inject Helper Method (end of class usually, or before fetch_option_chain)
    # Let's insert before fetch_option_chain
    if "async def fetch_option_chain" in content and "def fetch_orats_ivr" not in content:
        parts = content.split("async def fetch_option_chain")
        new_content = parts[0] + IVR_METHOD + "\n    async def fetch_option_chain" + parts[1]
        content = new_content
        print("Injected fetch_orats_ivr method.")
        
    # 2. Replace GET_CHAIN block
    if 'elif cmd == "GET_CHAIN":' in content:
        import re
        # Find the block until 'if cmd == "EXECUTE_SPREAD":' not really, usually 'continue'
        # Safest regex: elif cmd == "GET_CHAIN": ... continue
        pattern = r'(elif cmd == "GET_CHAIN":.*?continue)'
        
        # We need DOTALL
        match = re.search(pattern, content, re.DOTALL)
        if match:
            old_block = match.group(1)
            # Indentation fix: GET_CHAIN_BLOCK has 16 spaces? 
            # The file usually has 16 spaces inside the loop.
            # verify indentation of old_block
            
            # Let's blindly replace, assuming my string matches indentation roughly?
            # Creating strict replacement
            content = content.replace(old_block, GET_CHAIN_BLOCK.strip())
            print("Replaced GET_CHAIN logic.")
            
    with open(TS_FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_config()
    patch_ts_nexus()
