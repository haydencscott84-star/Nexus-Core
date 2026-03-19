import re

TARGET_FILE = "/root/trader_dashboard.py"

# CORRECT METHOD (4 spaces def, 8 spaces body)
CORRECT_METHOD = """    def calculate_net_delta(self):
        \"\"\"Calculates Net Delta and Gamma using cached ORATS Greeks + Live Price Adjustment.\"\"\"
        try:
            # Check if we have data
            if not hasattr(self, 'orats_chain') or self.orats_chain.empty:
                return 0.0, 0.0

            if not self.pos_map: return 0.0, 0.0

            net_delta = 0.0
            net_gamma = 0.0
            
            # Get Current Price
            try: curr_price = self.query_one(ExecutionPanel).und_price
            except: curr_price = 0
            
            if curr_price <= 0 and hasattr(self, 'fallback_price'): curr_price = self.fallback_price
            if curr_price <= 0: return 0.0, 0.0

            df = self.orats_chain
            
            for sym, pos in self.pos_map.items():
                qty = float(pos.get('qty', 0))
                if qty == 0: continue
                
                # Parse Symbol
                try:
                    parts = sym.split() 
                    raw = parts[1]
                    y = "20" + raw[:2]; m = raw[2:4]; d = raw[4:6]
                    expiry = f"{y}-{m}-{d}"
                    typ_char = raw[6]
                    typ = "CALL" if typ_char == "C" else "PUT"
                    strike = float(raw[7:])
                    
                    # MATCH ORATS
                    mask = (df['expiry'] == expiry) & (df['type'] == typ) & (abs(df['strike'] - strike) < 0.01)
                    row = df[mask]
                    
                    if not row.empty:
                        r = row.iloc[0]
                        ref_delta = float(r['delta']) 
                        ref_gamma = float(r['gamma']) 
                        ref_price = float(r['stockPrice'] or curr_price)
                        
                        curr_unit_delta = ref_delta + (ref_gamma * (curr_price - ref_price))

                        d, g = self.get_net_greeks(qty, curr_unit_delta, ref_gamma)
                        
                        net_delta += d
                        net_gamma += g
                        
                    else:
                        # Fallback (Only Delta)
                        pos_delta = float(pos.get('Delta', 0)) 
                        if pos_delta != 0:
                             net_delta += (qty * pos_delta * 100) 
                except Exception as ex: 
                    pass 

            return net_delta, net_gamma
        except Exception as e:
            return 0.0, 0.0"""

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    print("Replacing mis-indented calculate_net_delta...")
    
    # Regex to capture the mis-indented version (starts with 8+ spaces)
    # \s+def calculate_net_delta
    # We replace up to the next method or end of logic.
    # Logic usually ends with `except Exception as e: return 0.0, 0.0` or similar.
    # Let's match strictly the header and allow my string to replace the body.
    
    # Match: (whitespace)def calculate_net_delta(self): ... up to next def
    pattern = r"\s+def calculate_net_delta\(self\):.*?(?=\n\s+def|\n\s+async def|\n\s+class|\nif __name__)"
    
    new_content = re.sub(pattern, "\n" + CORRECT_METHOD, content, flags=re.DOTALL)
    
    with open(TARGET_FILE, 'w') as f:
        f.write(new_content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
