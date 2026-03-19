import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # The missing method
    fetch_method = """
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
"""

    # The updated calc method (same as before)
    calc_method = """
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

    # We need to replace the EXISTING `calculate_net_delta`
    # Let's try to match it line by line based on the signature.
    lines = content.splitlines()
    new_lines = []
    
    in_target = False
    replaced = False
    
    for line in lines:
        if "def calculate_net_delta(self):" in line:
            if not replaced:
                # Insert both methods here
                # Preserve indentation?
                # The line likely has indentation.
                indent = line[:line.find("def")]
                
                # We need to handle multi-line strings correctly if just appending.
                # But here we are building a list of strings.
                
                # Split our new methods into lines and add indentation
                f_lines = fetch_method.splitlines()
                c_lines = calc_method.splitlines()
                
                for l in f_lines:
                    # Strip first 4 spaces if present to avoid double indent if we add base indent?
                    # Actually valid python indentation is complex.
                    # Best to just assume standard 4 space.
                    if l.strip(): new_lines.append(l) # Using the string's own indent
                    else: new_lines.append("")

                for l in c_lines:
                    if l.strip(): new_lines.append(l)
                    else: new_lines.append("")
                
                in_target = True
                replaced = True
        elif in_target:
            # verify if we are still in the function.
            # Next line with same indentation as 'def' or less means out?
            # Or simplified: loop until we see another 'def' or 'async def' or 'if __name__'
            if line.strip().startswith("def ") or line.strip().startswith("async def ") or "if __name__" in line or "class " in line:
                if line.strip() != "def calculate_net_delta(self):": # Don't stop on our own line if we re-encountered?
                     in_target = False
                     new_lines.append(line)
            else:
                # Skip lines of the old method
                pass
        else:
            new_lines.append(line)

    if replaced:
        print("Replaced calculate_net_delta via line scan.")
        with open(TARGET_FILE, 'w') as f:
            f.write("\n".join(new_lines) + "\n")
        print("Success.")
    else:
        print("Failed to find calculate_net_delta line.")

if __name__ == "__main__":
    apply_fix()
