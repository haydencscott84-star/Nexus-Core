import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# Run grep non-interactively
cmd = "grep -C 50 'Nexus Credit Status' /root/nexus_spreads.py"

print(f"Connecting to {user}@{host}...")
# Note: passing command to ssh
child = pexpect.spawn(f'ssh {user}@{host} "{cmd}"', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    
    # Expect EOF (connection verify close)
    child.expect(pexpect.EOF, timeout=20)
    
    output = child.before
    print("--- GREP EXEC OUTPUT ---")
    print(output)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
