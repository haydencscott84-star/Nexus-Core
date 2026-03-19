import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# Python script to PATCH the logic
remote_patch_py = """
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f:
        content = f.read()
    
    # Target the start of the loop
    target = '                        k_long = data.get("long_strike", 0)'
    
    # We will replace the block inside the loop
    # The original code has:
    # is_put = (data.get("type") == "PUT")
    # strat_type = "Credit Put" if is_put else "Credit Call"
    # ...
    # if not is_credit:
    
    # We need to construct a robust replacement.
    # Since indentation is tricky, let's find the specific lines and replace them.
    
    lines = content.split('\\n')
    new_lines = []
    
    patch_applied = False
    
    for line in lines:
        if 'is_put = (data.get("type") == "PUT")' in line:
            # Replace logic
            indent = line[:line.find('is_put')]
            new_lines.append(f'{indent}is_call = data.get("is_call", False)')
            new_lines.append(f'{indent}is_put = not is_call')
            new_lines.append(f'{indent}is_credit = True # [FIX] Default to Credit for reporting')
            new_lines.append(f'{indent}strat_type = "Credit Put" if is_put else "Credit Call"')
            patch_applied = True
            # Skip the original line
            continue
            
        if 'strat_type =' in line and patch_applied and 'data.get' not in line:
             # Skip the old strat_type line that followed
             continue
             
        new_lines.append(line)
        
    if patch_applied:
        with open(path, 'w') as f:
            f.write('\\n'.join(new_lines))
        print("PATCH_SUCCESS")
    else:
        print("PATCH_TARGET_NOT_FOUND")
        
except Exception as e:
    print(f"ERROR: {e}")
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
    
    child.sendline("cat <<EOF > /root/patch_discord.py")
    child.sendline(remote_patch_py)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 /root/patch_discord.py")
    child.expect(['#', '$'], timeout=10)
    print(child.before)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
