import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Reset calculate_net_delta to SIMPLE debug
    # We replace the entire method definition.
    # We look for "def calculate_net_delta(self):"
    
    match = re.search(r"def calculate_net_delta\(self\):.*?(?=\n    def|\nclass)", content, re.DOTALL)
    
    simple_calc = """def calculate_net_delta(self):
        try:
             # Just iterate positions to prove we can read map
             count = len(self.pos_map) if self.pos_map else 0
             if count == 0: return 0.0
             return float(count) # Should show e.g. +25.0
        except: return -99.9"""

    if match:
        content = content.replace(match.group(0), simple_calc)
        print("Simplified calculate_net_delta.")
    else:
        # If regex fails, use string replacement of known previous version
        # Currently it has the "Sanity Check" version with "if not self.pos_map:"
        # We'll valid attempt a specific string replace
        pass

    # 2. Reset sub_mkt block (Remove TEST)
    # We look for the block we injected in force_clean_sub_mkt
    
    # "self.query_one('#m-delta', Metric).update_val('TEST', 'yellow')"
    
    # we replace that block with the clean version
    sub_mkt_clean = """try:
                 nd_init = self.calculate_net_delta()
                 self.query_one('#m-delta', Metric).update_val(f'{nd_init:+.1f}', '#8fbcbb')
                 except Exception as e: self.log_msg(f"[ERR] Init Delta: {e}")"""
                 
    # We need to construct the regex for the messy block
    # It contains "TEST", "yellow", and "log_msg" lines.
    
    # Let's just SEARCH for the line containing "'TEST', 'yellow'" and remove it?
    # And allow the subsequent logic to run.
    
    if "'TEST', 'yellow'" in content:
        # We want to remove that line.
        # It was: self.query_one('#m-delta', Metric).update_val('TEST', 'yellow')
        
        # We can just comment it out or delete it.
        content = re.sub(r"self\.query_one\('#m-delta', Metric\)\.update_val\('TEST', 'yellow'\)\n", "", content)
        print("Removed TEST update.")
    
    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
