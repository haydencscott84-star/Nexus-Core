
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f:
        content = f.read()
    
    lines = content.split('\n')
    new_lines = []
    
    inside_patch = False
    patch_applied = False
    
    for line in lines:
        if '# [FIX] Logic Patch Start' in line:
            inside_patch = True
            indent = line[:line.find('#')]
            new_lines.append(f'{indent}# [FIX] Logic Patch V2 Start')
            new_lines.append(f'{indent}is_put = (data.get("type") == "PUT")')
            new_lines.append(f'{indent}is_call = not is_put')
            new_lines.append(f'{indent}is_credit = True # [FIX] Force Credit')
            new_lines.append(f'{indent}strat_type = "Credit Put" if is_put else "Credit Call"')
            new_lines.append(f'{indent}# [FIX] Logic Patch V2 End')
            patch_applied = True
            continue
            
        if '# [FIX] Logic Patch End' in line:
            inside_patch = False
            continue
            
        if inside_patch:
            continue
            
        new_lines.append(line)
        
    if patch_applied:
        with open(path, 'w') as f:
            f.write('\n'.join(new_lines))
        print("REPATCH_SUCCESS")
    else:
        print("PATCH_MARKS_NOT_FOUND")

except Exception as e:
    print(f"ERROR: {e}")
