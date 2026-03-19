import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script_final = """
import sys
import os

path = '/root/analyze_snapshots.py'
try:
    with open(path, 'r') as f: content = f.read()
    print(f"Read {len(content)} chars.")
    
    target = 'try: prune_archived_data(days_keep=30)'
    replacement = '# [OPTIMIZATION] Moved to background\\n    # try: prune_archived_data(days_keep=30)'
    
    if target in content:
        print("Found target.")
        content = content.replace(target, replacement)
        
        # also fix the except
        target_except = '    except: pass'
        # This is risky if indentation varies.
        # Let's search for the line following the target
        
        with open(path, 'w') as f: f.write(content)
        print("PATCH_APPLIED_REPLACE")
    else:
        print("TARGET_NOT_FOUND")
        # Print nearby lines to debug
        lines = content.split('\\n')
        for line in lines:
            if 'prune' in line:
                print(f"Nearby: {repr(line)}")

except Exception as e:
    print(f"Error: {e}")
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
    
    child.sendline("cat <<EOF > patch_final_ver.py")
    child.sendline(remote_script_final)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_final_ver.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
