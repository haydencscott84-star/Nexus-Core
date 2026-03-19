
import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# We want to read the loop where 'managed_spreads' is assigned.
# We previously saw: self.managed_spreads[s_sym] = { ... }
# Let's find that line and read 50 lines BEFORE it to see the parsing logic.

cmd = """
import sys
try:
    with open('/root/nexus_spreads.py', 'r') as f:
        lines = f.readlines()
        
    target_line = -1
    for i, line in enumerate(lines):
        if 'self.managed_spreads[s_sym] =' in line:
            target_line = i
            break
            
    if target_line != -1:
        start = max(0, target_line - 60)
        end = min(len(lines), target_line + 20)
        print("___START_CODE___")
        for j in range(start, end):
            print(f"{j+1}: {lines[j].rstrip()}")
        print("___END_CODE___")
    else:
        print("TARGET_NOT_FOUND")
        
except Exception as e:
    print(f"ERROR: {e}")
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
    
    child.sendline("cat <<EOF > /root/read_debug.py")
    child.sendline(cmd)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 /root/read_debug.py")
    child.expect("___END_CODE___", timeout=20)
    
    out = child.before
    if "___START_CODE___" in out:
        print(out.split("___START_CODE___")[1])
    else:
        print(out)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)

