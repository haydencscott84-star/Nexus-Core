
import re

TS_FILE = "ts_nexus.py"
DEBIT_FILE = "nexus_debit.py"

def clean_ts():
    with open(TS_FILE, 'r') as f:
        lines = f.readlines()
        
    start_idx = 0
    for i, line in enumerate(lines):
        if line.startswith("import") or line.startswith("# FILE:") or line.startswith("# ---"):
            start_idx = i
            break
        # Heuristic: Skip lines with "spawn ssh" or "password:"
        if "spawn ssh" in line or "password:" in line:
            continue
            
    # Careful filter: Valid code might contain these strings? Unlikely at top level.
    # But let's find the first valid Python import or comment.
    
    clean_lines = lines[start_idx:]
    content = "".join(clean_lines)
    
    # --- OPTIMIZATION: Reduce Hammering ---
    # Find: expirations = r.json().get("Expirations", [])[:10]
    # Replace with: expirations = r.json().get("Expirations", [])[:3] # REDUCED TO 3
    if '[:10] # Next 10 expiries' in content:
        content = content.replace('[:10] # Next 10 expiries', '[:3] # Next 3 expiries')
        print("Optimized: Reduced expirations to 3.")
        
    # Find: if abs(val - center) < 75:
    # Replace with: if abs(val - center) < 30:
    if 'if abs(val - center) < 75:' in content:
        content = content.replace('if abs(val - center) < 75:', 'if abs(val - center) < 30: # Optimized Range')
        print("Optimized: Reduced strike scan range to 30.")
        
    # Ensure underlying_price support (patch_round2 logic) is present
    if "underlying_price=0.0" not in content:
        print("Re-applying underlying_price patch...")
        content = content.replace(
            "async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False):",
            "async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False, underlying_price=0.0):"
        )
        # Spot fallback
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
        
        # Command handler patching
        cmd_marker = 'data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw)'
        cmd_new = 'price = msg.get("price", 0.0)\n                    data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw, underlying_price=price)'
        content = content.replace(cmd_marker, cmd_new)

    with open(TS_FILE, 'w') as f:
        f.write(content)
    print("Cleaned and Optimized ts_nexus.py")

def clean_debit():
    with open(DEBIT_FILE, 'r') as f:
        content = f.read()
        
    # 1. Ensure CSS fix for width
    if "#width_input { width: 12; }" not in content:
        content = content.replace("#width_input { width: 8; }", "#width_input { width: 12; }")
        print("Fixed nexus_debit.py CSS width.")

    # 2. Ensure Payload sends Price
    # Check if price is in payload definition
    if '"price": self.current_spy_price' not in content:
        # Regex replacement (similar to patch_round2)
        content = re.sub(
            r'payload = \{"cmd": "GET_CHAIN".*?\}', 
            'payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "price": self.current_spy_price, "width": width}', 
            content
        )
        print("Updated nexus_debit.py payload with price.")

    with open(DEBIT_FILE, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    clean_ts()
    clean_debit()
