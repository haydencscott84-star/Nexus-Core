import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Define the methods to append
    # Note: Indentation must match the file.
    # Assuming standard 4 spaces.
    
    new_methods = """
    async def fetch_orats_greeks(self):
        \"\"\"Fetches live option chain from ORATS and caches it.\"\"\"
        try:
            self.log_msg("REQ: Fetching ORATS Greeks...")
            loop = asyncio.get_event_loop()
            # Run in thread/executor
            df = await loop.run_in_executor(None, get_live_chain, "SPY")
            
            if not df.empty:
                self.orats_chain = df
                self.log_msg(f"ORATS: Loaded {len(df)} contracts.")
                return True
            else:
                self.log_msg("ORATS: No data returned.")
                return False
        except Exception as e:
            self.log_msg(f"ORATS ERR: {e}")
            return False

    def calculate_net_delta(self):
        \"\"\"Calculates Net Delta using cached ORATS Greeks + Live Price Adjustment.\"\"\"
        try:
            # Check if we have data
            if not hasattr(self, 'orats_chain') or self.orats_chain.empty:
                return 0.0

            if not self.pos_map: return 0.0

            net_delta = 0.0
            
            try:
                curr_price = self.query_one(ExecutionPanel).und_price
            except: curr_price = 0
            
            if curr_price <= 0 and hasattr(self, 'fallback_price'):
                curr_price = self.fallback_price

            if curr_price <= 0: return 0.0

            df = self.orats_chain
            
            for sym, pos in self.pos_map.items():
                qty = float(pos.get('qty', 0))
                if qty == 0: continue
                
                try:
                    parts = sym.split() 
                    raw = parts[1]
                    y = "20" + raw[:2]; m = raw[2:4]; d = raw[4:6]
                    expiry = f"{y}-{m}-{d}"
                    typ_char = raw[6]
                    typ = "CALL" if typ_char == "C" else "PUT"
                    strike = float(raw[7:])
                    
                    mask = (df['expiry'] == expiry) & (df['type'] == typ) & (abs(df['strike'] - strike) < 0.01)
                    row = df[mask]
                    
                    if not row.empty:
                        r = row.iloc[0]
                        ref_delta = float(r['delta']) 
                        ref_gamma = float(r['gamma'])
                        ref_price = float(r['stockPrice'] or curr_price)
                        
                        adj_delta = (ref_delta * 100) + (ref_gamma * (curr_price - ref_price))
                        net_delta += (qty * adj_delta)
                    else:
                        pos_delta = float(pos.get('Delta', 0)) 
                        if pos_delta != 0: net_delta += (qty * pos_delta * 100)
                        
                except: pass

            return net_delta
        except Exception as e:
            self.log_msg(f"[ERR] Calc: {e}")
            return 0.0
    """

    # 2. Delete the misplaced methods block (approx 303 to 380)
    # We will look for the signature "async def fetch_orats_greeks(self):" appearing BEFORE "class TraderDashboardV2(App):"
    
    lines = content.splitlines()
    class_def_line = -1
    for i, line in enumerate(lines):
        if "class TraderDashboardV2(App):" in line:
            class_def_line = i
            break
            
    if class_def_line == -1:
        print("Could not find class TraderDashboardV2")
        return

    # Scan for garbage before class
    cleaned_lines = []
    skip = False
    
    misplaced_found = False
    
    for i, line in enumerate(lines):
        if i < class_def_line:
            if "async def fetch_orats_greeks(self):" in line:
                skip = True
                misplaced_found = True
                print("Found misplaced fetch_orats_greeks. Deleting block starting at line", i+1)
            
            if skip:
                # Heuristic to stop skipping:
                # If we hit the class def, stop (handled by i < class_def_line check kinda)
                # If we encounter another class or big gap?
                # Actually, simple heuristic:
                # If we see `class TraderDashboardV2` we stop (loop logic handles).
                # But we want to preserve other stuff.
                # Let's just delete everything from fetch_orats_greeks down to `class TraderDashboardV2`?
                # No, there might be other valid stuff.
                
                # Let's delete until we see a line that is NOT indented 4 spaces AND is not empty?
                # But misplaced methods are at 4 spaces indentation (in previous cat output).
                # Wait, they were in ExecutionPanel. 
                # ExecutionPanel ends... when?
                # The CAT output showed lines 300-325.
                # Line 286 was `def reset_trigger`.
                
                # Let's just blindly delete lines that match our method signatures + body.
                # Actually, easier:
                # Filter out the specific method definitions.
                pass
            
            # Simple Filter Logic:
            # If line contains `def fetch_orats_greeks` or `def calculate_net_delta`, skip.
            # And skip lines inside them...
            
            # Re-read: better to use string replace on the known block if possible.
            # But we generated the block dynamically in previous steps.
            
            # Let's stick to "Delete from 303 to 475" if that region is indeed garbage.
            # But assumes 303 is start.
            pass
    
    # NEW STRATEGY:
    # 1. Remove ANY occurrence of `def fetch_orats_greeks` and `def calculate_net_delta` from the file.
    # 2. Append them cleanly at the end of TraderDashboardV2.
    
    # 1. Regex Remove
    # Be careful not to remove the call `await self.fetch_orats_greeks()`.
    
    # Remove definitions:
    content = re.sub(r"async def fetch_orats_greeks\(self\):.*?(?=\s+def|\s+async def|\s+class|if __name__)", "", content, flags=re.DOTALL)
    content = re.sub(r"def calculate_net_delta\(self\):.*?(?=\s+def|\s+async def|\s+class|if __name__)", "", content, flags=re.DOTALL)
    
    print("Removed duplicate/misplaced method definitions.")
    
    # 2. Append to TraderDashboardV2
    # Find end of TraderDashboardV2
    # Look for `if __name__ == "__main__":`
    
    if 'if __name__ == "__main__":' in content:
        content = content.replace('if __name__ == "__main__":', new_methods + '\nif __name__ == "__main__":')
        print("Appended methods to App class.")
    else:
        print("Could not find main block to append.")
        # Try appending to EOF
        content += "\n" + new_methods

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
