import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script = """
import sys
try:
    with open('/root/nexus_spreads.py', 'r') as f:
        lines = f.readlines()
        
    found_lines = []
    for i, line in enumerate(lines):
        if "Nexus Credit Status" in line:
            start = max(0, i - 100)
            end = min(len(lines), i + 200) # Get a good chunk
            found_lines = lines[start:end]
            break
            
    if found_lines:
        with open('/root/debug_logic.txt', 'w') as f:
            f.writelines(found_lines)
    else:
        with open('/root/debug_logic.txt', 'w') as f:
            f.write("STRING_NOT_FOUND")
            
except Exception as e:
    with open('/root/debug_logic.txt', 'w') as error_f:
        error_f.write(str(e))
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
    
    # 1. Write the extractor script
    child.sendline("cat <<EOF > /root/extractor.py")
    child.sendline(remote_script)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    # 2. Run it
    child.sendline("python3 /root/extractor.py")
    child.expect(['#', '$'], timeout=20)
    
    # 3. Cat the result
    child.sendline("cat /root/debug_logic.txt")
    child.expect(['#', '$'], timeout=20)
    print("--- LOGIC CONTENT ---")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
