import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    # Run grep and ensure we capture it
    child.sendline("grep -n 'Nexus Credit Status' /root/nexus_spreads.py")
    child.expect(['#', '$'], timeout=10)
    grep_output = child.before.strip()
    print(f"GREP_RAW: {grep_output}")
    
    import re
    # Match the line number from the echoed command output or the result
    # Output might contain the command itself, so look for "number:content"
    lines = grep_output.split('\n')
    lineno = None
    for line in lines:
        m = re.search(r'^(\d+):', line.strip())
        if m:
            lineno = int(m.group(1))
            break
            
    if lineno:
        print(f"Found at line: {lineno}")
        start = max(1, lineno - 10)
        end = lineno + 80
        cmd_sed = f"sed -n '{start},{end}p' /root/nexus_spreads.py"
        child.sendline(cmd_sed)
        child.expect(['#', '$'], timeout=20)
        print(child.before)
    else:
        print("Could not parse line number.")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
