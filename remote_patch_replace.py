import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# Escaping for python string: " -> \"
# Escaping for shell: " -> \"
# Escaping for sed: " -> \"
# This is tricky.
# I'll use python on remote checking to apply the replace via file read/write to be 100% safe.

remote_script_final_replace = """
import sys
path = '/root/nexus_spreads.py'
with open(path, 'r') as f: content = f.read()

target = 'type_str = "PUT" if is_put else "CALL"'
replacement = 'try: s_id=short_sym.split(" ")[-1]; is_put=("P" in s_id) if "P" in s_id or "C" in s_id else is_put; except: pass; type_str = "PUT" if is_put else "CALL"'

if target in content and "s_id" not in content:
    content = content.replace(target, replacement)
    with open(path, 'w') as f: f.write(content)
    print("REPLACED_OK")
else:
    print("TARGET_NOT_FOUND_OR_ALREADY_DONE")

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
    
    child.sendline("cat <<EOF > patch_replace.py")
    child.sendline(remote_script_final_replace)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_replace.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
