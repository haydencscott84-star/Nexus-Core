
import os

target_file = "/root/nexus_debit.py"
print(f"Correcting UI IDs in {target_file}...")

updates = [
    ('#selected_setup_lbl', '#lbl_spread'),
    ('#debit_cost_lbl', '#lbl_debit'),
    ('#tgt_profit_lbl', '#lbl_profit'),
    ('#max_roc_lbl', '#lbl_roc'),
    ('#stop_sys_lbl', '#lbl_stop_trigger')
]

try:
    with open(target_file, 'r') as f:
        content = f.read()
        
    new_content = content
    count = 0
    for old, new in updates:
        if old in new_content:
            new_content = new_content.replace(old, new)
            count += 1
            print(f"Replaced {old} -> {new}")
            
    if count > 0:
        with open(target_file, 'w') as f:
            f.write(new_content)
        print(f"Successfully patched {count} ID references.")
    else:
        print("No faulty IDs found. Already patched?")

except Exception as e:
    print(f"Patch Error: {e}")
