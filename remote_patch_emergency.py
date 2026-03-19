import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# One liner python logic: 
# try: s=short_sym.split(" ")[-1]; is_put=("P" in s) if "P" in s or "C" in s else is_put; except: pass
# Indented with 16 spaces.

py_code = '                try: s=short_sym.split(" ")[-1]; is_put=("P" in s) if "P" in s or "C" in s else is_put; except: pass'

# Sed command to insert it before the type_str line.
# escaping for pexpect + shell + sed is hard.
# simpler: write a tiny python file remote, run it.

remote_script_writer = """
import sys
path = '/root/nexus_spreads.py'
with open(path, 'r') as f: lines = f.readlines()
new_lines = []
target = 'type_str = "PUT"'
inserted = False
for line in lines:
    if target in line and not inserted:
        new_lines.append('                try: s=short_sym.split(" ")[-1]; is_put=("P" in s) if "P" in s or "C" in s else is_put; except: pass\\n')
        inserted = True
    new_lines.append(line)
with open(path, 'w') as f: f.writelines(new_lines)
print("DONE")
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
    
    child.sendline("cat <<EOF > patch_emergency.py")
    child.sendline(remote_script_writer)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_emergency.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
