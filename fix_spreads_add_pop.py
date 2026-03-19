
TARGET_FILE = "/root/nexus_spreads.py"

POP_METHOD = """    def calculate_pop(self, spot, breakeven, dte, iv, strategy_type='bull'):
        try:
            if dte <= 0: dte = 0.0001
            t = dte / 365.0
            r = 0.0  # Risk free rate approx 0 locally or pass it in
            
            if iv <= 0: return 0.0
            
            ln_sk = math.log(spot / breakeven)
            drift = (r - 0.5 * iv**2) * t
            vol_term = iv * math.sqrt(t)
            
            d2 = (ln_sk + drift) / vol_term
            
            cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
            
            if strategy_type == 'bull':
                return cdf * 100
            else:
                return (1 - cdf) * 100
        except: return 0.0

"""

def add_pop_method():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        # Check if already exists (sanity check)
        if any("def calculate_pop" in l for l in lines):
            print("Method already exists.")
            return

        # Insert before populate_chain
        idx = -1
        for i, line in enumerate(lines):
            if "def populate_chain" in line:
                idx = i
                break
        
        if idx != -1:
            new_lines = lines[:idx] + [POP_METHOD] + lines[idx:]
            with open(TARGET_FILE, 'w') as f:
                f.writelines(new_lines)
            print("calculate_pop injected.")
        else:
            print("Could not find insertion point.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    import math
    add_pop_method()
