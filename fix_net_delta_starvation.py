import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # The issue: Delta only updates inside 'if p > 0' loop which relies on ZMQ.
    # We see SPY set with (C) in the fallback block. We must enable Delta there too.

    # LOCATE:
    # self.query_one("#m-spy", Metric).update_val(f"${self.fallback_price:.2f} (C)", "#ebcb8b")
    # self.query_one(ExecutionPanel).und_price = self.fallback_price
    
    target_str = 'self.query_one(ExecutionPanel).und_price = self.fallback_price'
    
    # We want to insert the delta update AFTER this line.
    
    payload = """
            self.query_one(ExecutionPanel).und_price = self.fallback_price
            
            # [PATCH] Force Initial Delta Update (Starvation Fix)
            try:
                nd_init = self.calculate_net_delta()
                self.query_one("#m-delta", Metric).update_val(f"{nd_init:+.1f}", "#8fbcbb")
            except Exception as e: self.log_msg(f"Init Delta Err: {e}")
"""
    
    if target_str in content:
        # Check if already patched to avoid duplication (though simple replace is safer)
        # We perform a strict replace of that single line with the block
        
        # NOTE: logic in sub_mkt fallback block:
        # if self.fallback_price > 0:
        #      update_val(...)
        #      und_price = ...  <-- TARGET
        
        # We need to be careful about indentation.
        # The target line usually has 12-16 spaces indentation.
        # We'll use regex or flexible replacement.
        
        # Let's find the specific line with exact whitespace if possible, or relax.
        # From previous 'cat' output (line 618):
        # "                 self.query_one(ExecutionPanel).und_price = self.fallback_price"
        
        # Regex to match the line ignoring leading whitespace
        pattern = r"(\s+)(self\.query_one\(ExecutionPanel\)\.und_price = self\.fallback_price)"
        
        match = re.search(pattern, content)
        if match:
            indent = match.group(1)
            original_line = match.group(0)
            
            # Construct replacement block with correct indentation
            # We want the new lines to have same indent
            new_block = original_line + "\n" + indent + "# [PATCH] Force Initial Delta Update\n" + \
                        indent + "try:\n" + \
                        indent + "    nd_init = self.calculate_net_delta()\n" + \
                        indent + "    self.query_one('#m-delta', Metric).update_val(f'{nd_init:+.1f}', '#8fbcbb')\n" + \
                        indent + "except: pass"
            
            content = content.replace(original_line, new_block)
            print("Patched Initial Fallback block.")
        else:
            print("Could not locate fallback line with regex.")
    else:
        print("Target string not found in file.")

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
