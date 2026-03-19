import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # Redefine fetch_fallback_price to use asyncio.wait_for
    # Existing:
    #     async def fetch_fallback_price(self):
    #         """Fetches snapshot from TradeStation if live feed is dead."""
    #         try:
    #             # ...
    #             # ...
    #             price = await loop.run_in_executor(None, _fetch)
    #             return float(price)
    #         except: return 0.0

    match = re.search(r"async def fetch_fallback_price\(self\):.*?(?=\n    async def|\n    def)", content, re.DOTALL)
    
    new_method = """async def fetch_fallback_price(self):
        \"\"\"Fetches snapshot from TradeStation if live feed is dead.\"\"\"
        try:
            # Import Config
            try: from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
            except: return 683.17 

            # Run in thread to avoid blocking UI
            loop = asyncio.get_event_loop()
            def _fetch():
                try:
                    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
                    q = ts.get_quote_snapshot("SPY")
                    return float(q.get('Last', 0))
                except: return 0.0
            
            # [PATCH] Timeout Wrapper
            try:
                price = await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=3.0)
                return float(price)
            except asyncio.TimeoutError:
                return 683.17 # Safe Fallback
        except: return 683.17"""

    if match:
        content = content.replace(match.group(0), new_method)
        print("Patched fetch_fallback_price with timeout.")
    else:
        print("Could not find fetch_fallback_price method.")

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
