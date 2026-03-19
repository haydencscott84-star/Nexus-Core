import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script = """
import sys

path = '/root/analyze_snapshots.py'
try:
    with open(path, 'r') as f: lines = f.readlines()
    
    new_lines = []
    patched_count = 0
    
    target_line = 'try: prune_archived_data(days_keep=30)'
    
    for line in lines:
        if target_line in line and '#' not in line.strip()[:1]:
            # Construct fix block (commented out)
            indent = line[:line.find('try')]
            fix = [
                f'{indent}# [OPTIMIZATION] Moved to background execution to prevent freeze\\n',
                f'{indent}# try: prune_archived_data(days_keep=30)\\n',
            ]
            new_lines.extend(fix)
            patched_count += 1
        elif 'except: pass' in line and patched_count > 0 and len(new_lines) > 0 and 'try: prune' in lines[lines.index(line)-1]:
             # comment out the except as well if it follows immediately
             indent = line[:line.find('except')]
             new_lines.append(f'{indent}# except: pass\\n')
        else:
             # Logic for the except is tricky if loop based. 
             # Simpler: just replace the exact block if found.
             pass
    
    # Let's use string replacement for safety like before.
    with open(path, 'r') as f: content = f.read()
    
    target_block = "    try: prune_archived_data(days_keep=30)\\n    except: pass"
    replacement_block = "    # [OPTIMIZATION] Moved to background execution to prevent freeze\\n    # try: prune_archived_data(days_keep=30)\\n    # except: pass"
    
    if target_block in content:
        content = content.replace(target_block, replacement_block)
        with open(path, 'w') as f: f.write(content)
        print("PATCH_SUCCESS_BLOCK")
    else:
        # Try finding just the call if indentation varies (it allows matching provided exact string)
        # Fallback to lines
        with open(path, 'w') as f: f.writelines(lines) # Restore if needed? No, lines weren't modified above effectively.
        print("TARGET_NOT_FOUND_EXACT_MATCH")
        
except Exception as e:
    print(e)
"""

# Actually, the block replacement is safest if indentation matches.
# I will use a super robust single-line logic replacer if I can.
# But let's try the block first. 
# Indentation in the file seemed to be 4 spaces in `load_unified_data`.

remote_script_v2 = """
import sys

path = '/root/analyze_snapshots.py'
with open(path, 'r') as f: content = f.read()

# Identifier for the line
target_fragment = "try: prune_archived_data(days_keep=30)"

if target_fragment in content and "[OPTIMIZATION]" not in content:
    lines = content.split('\\n')
    new_lines = []
    skip_next = False
    for i, line in enumerate(lines):
        if skip_next:
            skip_next = False
            continue
            
        if target_fragment in line:
            indent = line[:line.find('try')]
            new_lines.append(f'{indent}# [OPTIMIZATION] Moved to background execution to prevent freeze')
            new_lines.append(f'{indent}# try: prune_archived_data(days_keep=30)')
            # Check next line for except
            if i+1 < len(lines) and "except: pass" in lines[i+1]:
                 new_lines.append(f'{indent}# except: pass')
                 skip_next = True
        else:
            new_lines.append(line)
            
    with open(path, 'w') as f: f.write('\\n'.join(new_lines))
    print("PATCH_APPLIED_LINES")
else:
    print("PATCH_ALREADY_APPLIED_OR_NOT_FOUND")

"""

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("cat <<EOF > patch_snapshots.py")
    child.sendline(remote_script_v2)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_snapshots.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
