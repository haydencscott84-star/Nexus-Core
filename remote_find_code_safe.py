import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# Python script to run remotely
remote_py = """
import sys
try:
    with open('/root/nexus_spreads.py', 'r') as f:
        lines = f.readlines()
    
    found = False
    print("___START_CAPTURE___")
    for i, line in enumerate(lines):
        if "Nexus Credit Status" in line:
            print(f"MATCH: Line {i+1}")
            start = max(0, i - 20)
            end = min(len(lines), i + 40)
            for j in range(start, end):
                # Sanitize output to avoid confusion
                print(f"{j+1} | {lines[j].rstrip()}")
            found = True
            break
            
    if not found:
        print("NO_MATCH_FOUND_IN_FILE")
    print("___END_CAPTURE___")
        
except Exception as e:
    print(f"ERROR: {e}")
    print("___END_CAPTURE___")
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
    
    # Send the script to a file
    child.sendline("cat <<EOF > /root/find_code_safe.py")
    child.sendline(remote_py)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    # execute
    child.sendline("python3 /root/find_code_safe.py")
    # Wait for the unique marker
    child.expect("___END_CAPTURE___", timeout=20)
    
    output = child.before
    if "___START_CAPTURE___" in output:
        output = output.split("___START_CAPTURE___")[1]
        
    print("--- SAFE OUTPUT ---")
    print(output)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
