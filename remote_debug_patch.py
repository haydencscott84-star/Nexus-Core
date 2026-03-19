import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script = """
import sys

path = '/root/nexus_spreads.py'
with open(path, 'r') as f: lines = f.readlines()

print(f"Total lines: {len(lines)}")
for i, line in enumerate(lines):
    if "type_str" in line and "PUT" in line:
        print(f"Line {i+1}: {repr(line)}")
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
    
    child.sendline("cat <<EOF > debug_patch.py")
    child.sendline(remote_script)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 debug_patch.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
    child.sendline("rm debug_patch.py")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
