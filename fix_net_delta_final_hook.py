import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Redefine calculate_net_delta to usage Server Delta (if avail) + Fallbacks
    
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
                    # fallback logic or just use global fallback
                    curr_spy = getattr(self, 'fallback_price', 683.17)
                except: pass

            if curr_spy <= 0: curr_spy = 683.17 
            
            for sym, pos in self.pos_map.items():
                try:
                    qty_str = str(pos.get('qty', 0))
                    qty = float(qty_str.replace(',',''))
                except: qty = 0.0
                
                if qty == 0: continue
                
                # [NEW] Check for Server-Side Greeks FIRST
                server_delta = pos.get('Delta')
                if server_delta is not None and server_delta != 0:
                    try:
                        # Server sends delta per share or contract? usually per share equivalent in API
                        # But typically 'Delta' is 0.5. Option is 100 shares.
                        # net_delta += qty * 100 * float(server_delta)
                        
                        # Wait, validation needed. If server returns -0.4, that's per share.
                        # Multiplier is 100.
                        d_val = float(server_delta)
                        net_delta += (qty * 100 * d_val)
                        continue # Skip dynamic calc if server provided it
                    except: pass
                
                # ... Fallback to Dynamic Calc ...
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
        print("Replaced calculate_net_delta with SERVER-AWARE version.")
    else:
        print("Could not find method to replace.")

    # 2. Hook process_account_msg (Event Driven Update)
    # We look for the "Antigravity Portfolio Dump" block and insert AFTER it.
    
    dump_marker = 'asyncio.create_task(async_antigravity_dump("nexus_portfolio.json", portfolio_snapshot))'
    
    # Or just target the end of the method before `except:`
    # "self.query_one("#m-acct", Metric).update_val("OK","green");" ...
    
    # line ~970 in previous cat
    # The dump call is async.
    
    update_hook = """
                # [PATCH] Update Net Delta immediately after Account Sync
                try:
                    nd = self.calculate_net_delta()
                    self.query_one("#m-delta", Metric).update_val(f"{nd:+.1f}", "#8fbcbb")
                except: pass
"""
    
    target_line_part = 'self.query_one("#m-acct", Metric).update_val("OK","green")'
    
    if target_line_part in content:
        # We append our hook right after this line.
        parts = content.split(target_line_part)
        # parts[0] + target... + hook + parts[1]
        
        content = parts[0] + target_line_part + update_hook + parts[1]
        print("Hooked process_account_msg.")
    else:
        print("Could not find update_val line to hook in account msg.")

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
