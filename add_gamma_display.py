import re

TARGET_FILE = "/root/trader_dashboard.py"

# New calculate_net_delta (Tuple Return)
# Note: I'm reusing the logic from my text editor state, ensuring it returns both.
NEW_CALC_METHOD = """    def calculate_net_delta(self):
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
            return 0.0, 0.0
"""

# New Update Method (Display Logic)
NEW_UPDATE_METHOD = """    def _update_delta_safe(self):
        try:
            nd, ng = self.calculate_net_delta()
            # Format: "DELTA: +315 | Γ: -15"
            # Gamma Color: Red if < 0 (Risk), Green/Blue if > 0
            g_color = "#bf616a" if ng < 0 else "#a3be8c"
            
            # Since Metric usually takes one value, we construct a combined string.
            # But Metric 'update_val' might expect just the value part if label is static.
            # Looking at previous code: .update_val(f'{nd:+.1f}', '#8fbcbb')
            # It updates the VALUE displayed. The label "DELTA" is likely set in __init__.
            
            # We will hijack the value to show both.
            # Space might be tight. "D:+315 G:-15"
            label = f"{nd:+.0f} | Γ {ng:+.0f}"
            self.query_one('#m-delta', Metric).update_val(label, g_color)
            
        except Exception as e:
            self.log_msg(f"[ERR] Delta Update: {e}")
"""

def apply_patch():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # REPLACE calculate_net_delta
    # Regex to capture the whole method
    # It starts with `def calculate_net_delta(self):` and ends before next def.
    # Pattern: `def calculate_net_delta\(self\):.*?(?=\s+def|\s+async def|\s+class|if __name__)`
    print("Replacing calculate_net_delta...")
    content = re.sub(
        r"def calculate_net_delta\(self\):.*?(?=\n\s+def|\n\s+async def|\n\s+class|\nif __name__)", 
        NEW_CALC_METHOD, 
        content, 
        flags=re.DOTALL
    )

    # REPLACE _update_delta_safe
    print("Replacing _update_delta_safe...")
    content = re.sub(
        r"def _update_delta_safe\(self\):.*?(?=\n\s+def|\n\s+async def|\n\s+class|\nif __name__)", 
        NEW_UPDATE_METHOD, 
        content, 
        flags=re.DOTALL
    )

    print("Writing file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_patch()
