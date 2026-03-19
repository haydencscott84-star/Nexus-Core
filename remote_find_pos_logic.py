import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"
file_path = "/root/nexus_spreads.py"

# Find where pos_table is updated
cmd = f"grep -nC 10 'pos_table.add_row' {file_path}"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host} "{cmd}"', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(pexpect.EOF, timeout=30)
    print("Output:")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
