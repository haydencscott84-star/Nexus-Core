import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # We will redefine calculate_net_delta with heavy file logging
    debug_calc = """
    def calculate_net_delta(self):
        \"\"\"Calculates Net Delta using cached ORATS Greeks + Live Price Adjustment.\"\"\"
        try:
            with open("/root/delta_debug.log", "a") as f:
                f.write(f"--- Calc Run ---\\n")
                
                # Check Data
                if not hasattr(self, 'orats_chain'):
                    f.write("FAIL: No orats_chain attr\\n")
                    return 0.0
                if self.orats_chain.empty:
                    f.write("FAIL: orats_chain is empty\\n")
                    return 0.0
                
                f.write(f"ORATS Chain Size: {len(self.orats_chain)}\\n")

                if not self.pos_map:
                    f.write("FAIL: No positions in pos_map\\n")
                    return 0.0

                net_delta = 0.0
                
                try:
                    curr_price = self.query_one(ExecutionPanel).und_price
                except: curr_price = 0
                
                if curr_price <= 0 and hasattr(self, 'fallback_price'):
                    curr_price = self.fallback_price
                
                f.write(f"Ref Price: {curr_price}\\n")

                df = self.orats_chain
                
                for sym, pos in self.pos_map.items():
                    f.write(f"Processing {sym}...\\n")
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
                        
                        f.write(f"Parsed: Exp={expiry}, Typ={typ}, Strk={strike}\\n")
                        
                        mask = (df['expiry'] == expiry) & (df['type'] == typ) & (abs(df['strike'] - strike) < 0.01)
                        row = df[mask]
                        
                        if not row.empty:
                            r = row.iloc[0]
                            ref_delta = float(r['delta']) 
                            ref_gamma = float(r['gamma'])
                            ref_price = float(r['stockPrice'] or curr_price)
                            
                            adj_delta = (ref_delta * 100) + (ref_gamma * (curr_price - ref_price))
                            net_delta += (qty * adj_delta)
                            f.write(f"MATCH: {sym} -> RefDelta={ref_delta}, AdjDelta={adj_delta}, Net+={qty*adj_delta}\\n")
                        else:
                            f.write(f"NO MATCH ORATS for {sym}\\n")
                            pos_delta = float(pos.get('Delta', 0)) 
                            if pos_delta != 0: net_delta += (qty * pos_delta * 100)
                            
                    except Exception as ex: 
                        f.write(f"Parse Error for {sym}: {ex}\\n")

                f.write(f"Total Net Delta: {net_delta}\\n")
                return net_delta
        except Exception as e:
            # self.log_msg(f"[ERR] Calc: {e}")
            return 0.0
    """

    # Replace existing method
    # Use generic regex replacement again
    content = re.sub(r"def calculate_net_delta\(self\):.*?(?=\s+def|\s+async def|\s+class|if __name__)", "", content, flags=re.DOTALL)
    
    # Append new debug one before main
    if 'if __name__ == "__main__":' in content:
        content = content.replace('if __name__ == "__main__":', debug_calc + '\nif __name__ == "__main__":')
    else:
        content += "\n" + debug_calc

    print("Writing debug version...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
