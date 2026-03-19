import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Modify sub_mkt to force "TEST"
    # We look for the try block we rescued.
    # "try:\n    nd_init = self.calculate_net_delta()"
    
    # We will insert a sanity update BEFORE calculate_net_delta
    
    tgt = "nd_init = self.calculate_net_delta()"
    rep = """self.query_one('#m-delta', Metric).update_val('TEST', 'yellow')
                    nd_init = self.calculate_net_delta()"""
    
    content = content.replace(tgt, rep)
    
    # 2. Modify calculate_net_delta to check for EMPTY pos_map
    
    tgt2 = "if curr_spy <= 0: curr_spy = 683.17"
    rep2 = """if curr_spy <= 0: curr_spy = 683.17
            
            if not self.pos_map:
                try: self.query_one('#m-delta', Metric).update_val('EMPTY', 'red')
                except: pass
                return 0.0
"""
    
    content = content.replace(tgt2, rep2)
    
    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
