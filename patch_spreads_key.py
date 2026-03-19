
# Patch nexus_spreads.py to update key aggregation logic
import os

target_file = "/root/nexus_spreads.py"
print(f"Patching {target_file}...")

try:
    with open(target_file, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    patched_key = False
    
    for line in lines:
        if 'key = f"{short_strike}|{long_strike}|{credit}|{short_strike}|{long_strike}|{width}"' in line:
            print("Found old key line! Replacing...")
            # Use EXACT whitespace preservation if possible, or standard indentation
            indent = line.split('key =')[0]
            new_line = f'{indent}key = f"{{s[\'expiry\']}}|{{short_strike}}|{{long_strike}}|{{credit}}|{{width}}|{{is_put_credit}}"\n'
            new_lines.append(new_line)
            patched_key = True
        else:
            new_lines.append(line)
            
    if patched_key:
        with open(target_file, 'w') as f:
            f.writelines(new_lines)
        print("Successfully patched key logic.")
    else:
        print("ERROR: Could not find target key line. Script may already be patched.")

except Exception as e:
    print(f"Patch Error: {e}")
