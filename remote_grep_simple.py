import pexpect
import sys
import time

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

cmd = "grep -C 20 'Nexus Credit Status' /root/nexus_spreads.py"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    # Send command
    child.sendline(cmd)
    
    # Wait for output
    # match prompt again
    child.expect(['#', '$'], timeout=20)
    
    output = child.before
    print("--- GREP OUTPUT ---")
    print(output)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
