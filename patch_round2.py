
import re

TS_FILE = "ts_nexus.py"
DEBIT_FILE = "nexus_debit.py"

def patch_ts():
    with open(TS_FILE, 'r') as f: content = f.read()
    
    # 1. Update method signature to accept underlying_price
    # Old: async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False):
    # New: async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False, underlying_price=0.0):
    
    if "underlying_price=0.0" not in content:
        content = content.replace(
            "async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False):",
            "async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False, underlying_price=0.0):"
        )
        
        # 2. Update logic to use it
        # Old: spot_price = 0.0 ... try ... q_spot ...
        # New: spot_price = underlying_price if underlying_price > 0 else 0.0 ...
        
        spot_logic_old = """            # 2. Get Current Spot Price (for Delta Calc)
            spot_price = 0.0
            try:
                q_spot = await asyncio.to_thread(self.TS.get_quote_snapshot, ticker)
                spot_price = float(q_spot.get("Last", 0))
            except: pass"""
            
        spot_logic_new = """            # 2. Get Current Spot Price (for Delta Calc)
            spot_price = underlying_price
            if spot_price <= 0:
                try:
                    q_spot = await asyncio.to_thread(self.TS.get_quote_snapshot, ticker)
                    spot_price = float(q_spot.get("Last", 0))
                except: pass"""
                
        content = content.replace(spot_logic_old, spot_logic_new)
        
        # 3. Update Command Handler to extract it
        # Old: raw = msg.get('raw', False)
        # Old: data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw)
        
        # We need to find the command handler block. It's inside message loop.
        # It looks like:
        # if cmd == "GET_CHAIN":
        #    ...
        #    raw = msg.get('raw', False)
        #    data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw)
        
        cmd_marker = 'data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw)'
        cmd_new = 'price = msg.get("price", 0.0)\n                    data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw, underlying_price=price)'
        
        content = content.replace(cmd_marker, cmd_new)
        
        print("Patched ts_nexus.py for underlying_price")
        
    with open(TS_FILE, 'w') as f: f.write(content)

def patch_debit():
    with open(DEBIT_FILE, 'r') as f: content = f.read()
    
    # 1. Update CSS for Width Input (Fix UI Cutoff)
    # Old: #width_input { width: 8; }
    # New: #width_input { width: 12; }
    content = content.replace("#width_input { width: 8; }", "#width_input { width: 12; }")
    content = content.replace("#width_input { width: 30; }", "#width_input { width: 12; }") # Previous default was value="30", check CSS
    
    # Wait, the CSS in STEP 1302 had: #width_input { width: 8; }
    # In Step 1302 the value was "30" in the HTML/Compose.
    
    # 2. Update fetch_chain to send price
    # Old: payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_}
    # New: payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "price": self.current_spy_price}
    # Also include raw=True which was added in previous patch, but let's be safe.
    
    # Previous patch: '"cmd": "GET_CHAIN", "raw": True'
    # So finding that line:
    payload_old = 'payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_}'
    # It might have been modified by previous patch to:
    # payload = {"cmd": "GET_CHAIN", "raw": True, "ticker": "SPY", "type": type_} ? 
    # The previous patch used replace on the string literal.
    
    # Let's simple search and replace the line if strict match fails
    if 'payload = {"cmd": "GET_CHAIN"' in content:
        # Regex to match the dict definition
        content = re.sub(
            r'payload = \{"cmd": "GET_CHAIN".*?\}', 
            'payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "price": self.current_spy_price, "width": width}', 
            content
        )
        print("Patched nexus_debit.py payload")
        
    with open(DEBIT_FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_ts()
    patch_debit()
