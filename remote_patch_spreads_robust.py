import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script = """
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f: lines = f.readlines()
    
    new_lines = []
    patched_count = 0
    
    # We want to match: is_put = spread_data.get("is_put", False)
    # And insert code after it.
    
    for line in lines:
        new_lines.append(line)
        if 'spread_data.get("is_put", False)' in line and 'is_put =' in line:
            # Found it. Calculate indentation.
            indent = line[:line.find('is_put')]
            
            # Construct fix block
            fix = [
                f'{indent}# [FIX] Override based on Symbol ID (Source of Truth)\\n',
                f'{indent}try:\\n',
                f'{indent}    short_id = short_sym.split(" ")[-1]\\n',
                f'{indent}    if "C" in short_id and "P" not in short_id: is_put = False\\n',
                f'{indent}    elif "P" in short_id and "C" not in short_id: is_put = True\\n',
                f'{indent}except: pass\\n'
            ]
            new_lines.extend(fix)
            patched_count += 1
            
    if patched_count > 0:
        with open(path, 'w') as f: f.writelines(new_lines)
        print(f"PATCH_SUCCESS_{patched_count}")
    else:
        print("PATCH_TARGET_NOT_FOUND")

except Exception as e:
    print(e)
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
    
    child.sendline("cat <<EOF > patch_spreads_robust.py")
    child.sendline(remote_script)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_spreads_robust.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
    child.sendline("rm patch_spreads_robust.py")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
