import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# We want to find the line number first, then read context.
cmd_grep = "grep -n 'Nexus Credit Status' /root/nexus_spreads.py"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    child.sendline(cmd_grep)
    child.expect(['#', '$'], timeout=10)
    output = child.before.strip()
    print(f"Grep Output: {output}")
    
    # Extract line number
    import re
    match = re.search(r'(\d+):', output)
    if match:
        lineno = int(match.group(1))
        start = max(1, lineno - 20)
        end = lineno + 100 # Read enough to see the loop/logic
        
        cmd_read = f"sed -n '{start},{end}p' /root/nexus_spreads.py"
        print(f"--- Reading lines {start}-{end} ---")
        child.sendline(cmd_read)
        # sed output might be large, handle it
        child.expect(['#', '$'], timeout=20)
        print(child.before.strip())
        
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
except Exception as e:
    print(e)
