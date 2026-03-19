import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script = """
import sys
try:
    with open('/root/nexus_spreads.py', 'r') as f: lines = f.readlines()
    out = []
    found = False
    for line in lines:
        if 'type_str = "PUT"' in line and not found and '[FIX]' not in line:
            indent = line[:line.find('type_str')]
            out.append(f'{indent}# [FIX] AUTO TYPE\\n')
            out.append(f'{indent}try:\\n')
            out.append(f'{indent}    s_id = short_sym.split(" ")[-1]\\n')
            out.append(f'{indent}    if "C" in s_id and "P" not in s_id: is_put = False\\n')
            out.append(f'{indent}    elif "P" in s_id and "C" not in s_id: is_put = True\\n')
            out.append(f'{indent}except: pass\\n')
            out.append(line)
            found = True
        else:
            out.append(line)
    
    if found:
        with open('/root/nexus_spreads.py', 'w') as f: f.writelines(out)
        print("PATCH_APPLIED_SUCCESS")
    else:
        print("PATCH_NOT_FOUND_OR_DONE")

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
    
    child.sendline("cat <<EOF > patch_spreads_v3.py")
    child.sendline(remote_script)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_spreads_v3.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
    child.sendline("rm patch_spreads_v3.py")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
