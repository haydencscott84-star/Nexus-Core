
import os

target_file = "/root/nexus_debit.py"
print(f"Injecting Profit Logic into {target_file}...")

# Logic to inject
profit_code = """                    
                    # [PATCH] Profit Target Check
                    if roi >= 50.0 and self.auto_exit_enabled:
                         if self.managed_spreads.get(l_sym):
                             self.log_msg(f"ðŸ’¸ Profit Target Hit: {l_sym} (+{roi:.1f}%)")
                             asyncio.create_task(self.panic_close_spread(self.managed_spreads[l_sym], reason="PROFIT_TAKE"))
"""

try:
    with open(target_file, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    injected_count = 0
    
    # Target line: pl_str = f"{roi:+.1f}%"
    # This appears twice (Call Loop and Put Loop)
    
    for line in lines:
        new_lines.append(line)
        if 'pl_str = f"{roi:+.1f}%"' in line:
            print(f"Found insertion point {injected_count + 1}...")
            # Detect indentation from the target line
            indent = line.split('pl_str')[0]
            # Add indented code
            new_lines.append(profit_code.replace("                    ", indent)) 
            injected_count += 1
            
    if injected_count == 2:
        with open(target_file, 'w') as f:
            f.writelines(new_lines)
        print("Successfully injected profit logic twice (Calls and Puts).")
    else:
        print(f"WARNING: Expected 2 insertions, but found {injected_count}. Check file format.")

except Exception as e:
    print(f"Injection Error: {e}")
