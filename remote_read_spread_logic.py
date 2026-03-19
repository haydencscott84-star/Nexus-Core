import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_code = """
import sys
try:
    with open('/root/nexus_spreads.py', 'r') as f:
        lines = f.readlines()
        
    found = False
    for i, line in enumerate(lines):
        if "Nexus Credit Status" in line:
            print(f"MATCH_FOUND_AT_LINE_{i}")
            start = max(0, i - 50)
            end = min(len(lines), i + 100)
            print("--- BEGIN SNIPPET ---")
            for j in range(start, end):
                print(f"{j+1}: {lines[j].rstrip()}")
            print("--- END SNIPPET ---")
            found = True
            break
            
    if not found:
        print("STRING_NOT_FOUND")
        
except Exception as e:
    print(f"Error: {e}")
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
    
    child.sendline("cat <<EOF > /root/debug_discord_read.py")
    child.sendline(remote_code)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 /root/debug_discord_read.py")
    child.expect(['#', '$'], timeout=10)
    print(child.before)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
