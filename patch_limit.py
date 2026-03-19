
import re

DEBIT_FILE = "nexus_debit.py"

NEW_POPULATE_METHOD = """    def populate_debit_chain(self, chain_data, width):
        table = self.query_one("#chain_table", DataTable)
        table.clear()
        
        # 1. IDENTIFY CANDIDATES (Long Legs with Delta 0.65-0.80)
        long_candidates = []
        for opt in chain_data:
            delta = abs(float(opt.get('delta', 0)))
            if 0.65 <= delta <= 0.80:
                long_candidates.append(opt)
        
        # 2. BUILD SPREADS
        spread_setups = []
        for long_leg in long_candidates:
            # Determine Target Short Strike
            l_strike = float(long_leg['strike'])
            delta_val = float(long_leg['delta'])
            
            if delta_val < 0: # PUT
                t_short = l_strike - width
            else: # CALL
                t_short = l_strike + width
            
            # Find Short Leg in chain_data
            short_leg = next((x for x in chain_data if abs(float(x['strike']) - t_short) < 0.5 and x['expiry'] == long_leg['expiry']), None)
            
            if short_leg:
                # Calc Metrics
                # Debit = Ask(Long) - Bid(Short)
                debit = float(long_leg['ask']) - float(short_leg['bid'])
                if debit <= 0: continue # Invalid or Arb
                
                max_profit = width - debit
                roc = (max_profit / debit) * 100
                
                spread_setups.append({
                    "long": long_leg,
                    "short": short_leg,
                    "debit": debit,
                    "profit": max_profit,
                    "roc": roc
                })
        
        # 3. SORT & LIMIT (Top 20 by ROC)
        spread_setups.sort(key=lambda x: x['roc'], reverse=True)
        top_picks = spread_setups[:20]
        
        # 4. POPULATE TABLE
        for s in top_picks:
            l = s['long']; sh = s['short']
            roc = s['roc']
            
            roc_style = "bold green" if roc > 80 else "bold yellow"
            
            row = [
                l["expiry"], str(l["dte"]), 
                f"{l['strike']} (L)", f"{sh['strike']} (S)",
                f"${s['debit']:.2f}", f"${s['profit']:.2f}",
                Text(f"{roc:.1f}%", style=roc_style),
                f"{float(l['delta']):.2f}"
            ]
            
            key = f"{l['symbol']}|{sh['symbol']}|{s['debit']}|{l['strike']}|{sh['strike']}|{width}"
            table.add_row(*row, key=key)
            
        self.log_msg(f"Showing Top {len(top_picks)} of {len(spread_setups)} setups.")
"""

def patch_debit_limit():
    with open(DEBIT_FILE, 'r') as f: content = f.read()
    
    # Replace the populate_debit_chain method
    # Pattern: def populate_debit_chain(self, chain_data, width): ... till end of method ...
    # But regex for method replacement is tricky.
    
    # We find the start of the method
    start_str = "    def populate_debit_chain(self, chain_data, width):"
    
    if start_str in content:
        start_idx = content.find(start_str)
        # Find the next method "def on_data_table_row_selected"
        end_str = "    def on_data_table_row_selected"
        end_idx = content.find(end_str)
        
        if end_idx == -1:
             print("Could not find end of method.")
             return

        # Replace
        new_content = content[:start_idx] + NEW_POPULATE_METHOD + "\n" + content[end_idx:]
        
        with open(DEBIT_FILE, 'w') as f: f.write(new_content)
        print("Patched nexus_debit.py with Top 20 Limit logic.")
    else:
        print("Could not find populate_debit_chain method.")

if __name__ == "__main__":
    patch_debit_limit()
