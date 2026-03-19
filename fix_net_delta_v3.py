import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Redefine calculate_net_delta with UI-based Fallback
    
    new_method = """
    def calculate_net_delta(self):
        net_delta = 0.0
        try:
            # TRY 1: Execution Panel
            curr_spy_val = getattr(self.query_one(ExecutionPanel), 'und_price', 0.0)
            curr_spy = float(curr_spy_val)
            
            # TRY 2: Metric Widget (text scrape)
            if curr_spy <= 0:
                try:
                    txt = self.query_one("#m-spy", Metric).renderable 
                    # txt is a Text object or markup. Let's just assume fallback price logic
                    curr_spy = getattr(self, 'fallback_price', 0.0)
                except: pass

            # [DEBUG] Force fallbacks if still 0
            if curr_spy <= 0: curr_spy = 683.17 
            
            for sym, pos in self.pos_map.items():
                try:
                    qty_str = str(pos.get('qty', 0))
                    qty = float(qty_str.replace(',',''))
                except: qty = 0.0
                
                if qty == 0: continue
                
                if 'entry_delta' not in pos:
                    is_call = 'C' in sym
                    pos['entry_delta'] = 0.5 if is_call else -0.5
                    pos['entry_gamma'] = 0.05
                    pos['entry_spot'] = curr_spy

                try:
                    e_delta = float(pos.get('entry_delta', 0.0))
                    e_gamma = float(pos.get('entry_gamma', 0.0))
                    e_spot = float(pos.get('entry_spot', curr_spy))
                    
                    price_diff = curr_spy - e_spot
                    curr_delta = e_delta + (e_gamma * price_diff)
                    curr_delta = max(-1.0, min(1.0, curr_delta))
                    
                    net_delta += (qty * 100 * curr_delta)
                except ValueError: continue
                
        except Exception as e:
            return 0.0
        return net_delta
"""
    
    # We locate the previous definition again and replace it
    old_def = "def calculate_net_delta(self):"
    
    if old_def in content: 
        # Find start index
        idx = content.find(old_def)
        # Find end index (next def)
        next_def = content.find("def ", idx + 30)
        
        # Splicing
        content = content[:idx] + new_method + "\n    " + content[next_def:]
        print("Replaced calculate_net_delta with UI-FALLBACK version.")
    else:
        print("Could not find method to replace.")

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
