
TARGET_FILE = "/root/nexus_spreads.py"

def fix_final():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        skip = False
        
        for line in lines:
            stripped = line.strip()
            
            # Detect start of calculate_pop (likely at 8 spaces currently)
            if "def calculate_pop" in line:
                # We want to insert the CORRECT version here
                # And skip the old lines until we hit populate_chain
                skip = True
                
                # Correct indentation (4 spaces for def, 8 for body)
                clean_pop = [
                    "    def calculate_pop(self, spot, breakeven, dte, iv, strategy_type='bull'):\n",
                    "        try:\n",
                    "            # Handle Edge Cases\n",
                    "            if dte <= 0:\n",
                    "                if strategy_type == 'bull':\n",
                    "                    return 100.0 if spot > breakeven else 0.0\n",
                    "                else:\n",
                    "                    return 100.0 if spot < breakeven else 0.0\n",
                    "            \n",
                    "            # Constants\n",
                    "            t = dte / 365.0\n",
                    "            r = 0.045\n",
                    "            \n",
                    "            if iv == 0 or t == 0 or spot <= 0 or breakeven <= 0: return 0.0\n",
                    "            \n",
                    "            # Black-Scholes d2 term\n",
                    "            ln_sk = math.log(spot / breakeven)\n",
                    "            drift = (r - 0.5 * iv**2) * t\n",
                    "            vol_term = iv * math.sqrt(t)\n",
                    "            \n",
                    "            d2 = (ln_sk + drift) / vol_term\n",
                    "            \n",
                    "            cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))\n",
                    "            \n",
                    "            if strategy_type == 'bull':\n",
                    "                return cdf * 100\n",
                    "            else:\n",
                    "                return (1 - cdf) * 100\n",
                    "        except: return 0.0\n",
                    "\n"
                ]
                new_lines.extend(clean_pop)
                continue
            
            # Stop skipping when we hit populate_chain
            if skip:
                if "def populate_chain" in line:
                    skip = False
                    new_lines.append(line)
                continue
            
            # Normal line
            new_lines.append(line)

        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Final Fix Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_final()
