import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

cmd = "head -n 20 /root/nexus_spreads.py"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    child.sendline(cmd)
    child.expect(['#', '$'], timeout=10)
    print(child.before)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
