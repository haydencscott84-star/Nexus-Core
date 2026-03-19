import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        lines = f.readlines()

    # We want to replace the mess around "Force Initial Delta Update"
    # Identify the start and end of the MESS.
    
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if "[PATCH] Force Initial Delta Update" in line:
            start_idx = i
        if start_idx != -1 and "while True:" in line and i > start_idx:
            end_idx = i
            break
            
    if start_idx != -1 and end_idx != -1:
        print(f"Replacing Lines {start_idx} to {end_idx}")
        
        # Keep the start marker
        new_block = [lines[start_idx]] 
        
        # Base Indent: 17 spaces (taken from previous context)
        # "                 "
        base_indent = "                 "
        inner_indent = base_indent + "    " # 21 spaces
        
        # Construct the CLEAN block
        new_block.append(base_indent + "try:\n")
        new_block.append(inner_indent + "self.query_one('#m-delta', Metric).update_val('TEST', 'yellow')\n")
        new_block.append(inner_indent + "nd_init = self.calculate_net_delta()\n")
        new_block.append(inner_indent + 'self.log_msg(f"[DEBUG] Init Delta: {nd_init}")\n')
        new_block.append(inner_indent + "self.query_one('#m-delta', Metric).update_val(f'{nd_init:+.1f}', '#8fbcbb')\n")
        new_block.append(base_indent + 'except Exception as e: self.log_msg(f"[ERR] Init Delta: {e}")\n')
        new_block.append("\n") # Spacer
        
        # Reassemble
        final_lines = lines[:start_idx] + new_block + lines[end_idx:]
        
        print("Writing fixed file...")
        with open(TARGET_FILE, 'w') as f:
            f.writelines(final_lines)
        print("Success.")
    else:
        print("Could not find block boundaries.")

if __name__ == "__main__":
    apply_fix()
