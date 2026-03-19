
import sys
import os

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f:
        content = f.read()
    
    # We are looking for the loop start to inject our variables
    # The snippet we saw earlier:
    # k_short = data.get("short_strike", 0)
    # k_long = data.get("long_strike", 0)
    
    # We want to replace the logic that follows immediately.
    # The original file has:
    #                     k_long = data.get("long_strike", 0)
    #                     is_put = (data.get("type") == "PUT")
    
    # We'll use replace() for exact string match if possible, or build lines.
    # Since we don't have the full file guaranteed locally, let's use the line-scanning approach from before.
    
    lines = content.split('\n')
    new_lines = []
    patch_applied = False
    
    target_marker = 'data.get("type") == "PUT"'
    
    for i, line in enumerate(lines):
        if target_marker in line and not patch_applied:
            # We found the line: is_put = (data.get("type") == "PUT")
            # Let's get indentation
            indent = line[:line.find('is_put')]
            
            # Insert our fix BLOCK
            new_lines.append(f'{indent}# [FIX] Logic Patch Start')
            new_lines.append(f'{indent}is_call = data.get("is_call", False)')
            new_lines.append(f'{indent}is_put = not is_call')
            new_lines.append(f'{indent}is_credit = True # [FIX] Force Credit for reporting')
            new_lines.append(f'{indent}strat_type = "Credit Put" if is_put else "Credit Call"')
            new_lines.append(f'{indent}# [FIX] Logic Patch End')
            
            patch_applied = True
            # We skip the original line.
            # We also need to skip the NEXT line which was `strat_type = ...`
            # But the loop processes line by line. We can just skip lines that look like the old logic if we haven't written them yet?
            # Or simpler: The next iteration will see `strat_type = ...`
            # We should probably filter it out if it matches the old broken one.
            continue
            
        if 'strat_type =' in line and patch_applied:
             # This is the old line following our target. Skip it.
             # But wait, what if there are other strat_types? 
             # The one we want to replace is `strat_type = "Credit Put" if is_put else "Credit Call"`
             # Actually, our new code adds it. So we can just skip it.
             # To be safe, let's only skip the one immediately following (or close to) our patch.
             # Since we just patched, let's skip this valid line (it's redundant now but maybe harmless? No, we defined variables differently).
             # The old code used `data.get("type")` which we replaced.
             # Let's effectively duplicate the variable assignment? No.
             # Let's comment it out.
             new_lines.append(f'{line.replace("strat_type", "# OLD_strat_type")}')
             continue

        new_lines.append(line)
        
    if patch_applied:
        with open(path, 'w') as f:
            f.write('\n'.join(new_lines))
        print("PATCH_SUCCESS")
    else:
        print("PATCH_TARGET_NOT_FOUND")
        # debug
        print(f"Content length: {len(content)}")
        print(f"Sample line: {[l for l in lines if 'type' in l][:3]}")

except Exception as e:
    print(f"ERROR: {e}")
