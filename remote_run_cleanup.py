import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

local_file = "archive_cleanup.py"
remote_file = "/root/archive_cleanup.py"

print(f"Reading {local_file}...")
with open(local_file, 'r') as f:
    content = f.read()

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    # Upload via cat
    child.sendline(f"cat > {remote_file} << 'EOF'")
    child.sendline(content)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=20)
    
    print("Running cleanup script...")
    child.sendline(f"python3 {remote_file}")
    
    # This might take a while, using loop to print output
    while True:
        try:
            # Expect newline or prompt
            index = child.expect(['\r\n', '#', '$'], timeout=300) 
            if index == 0:
                line = child.before.strip()
                if line: print(line)
            else:
                print(child.before.strip())
                break
        except pexpect.TIMEOUT:
            print("Timeout waiting for output...")
            break
            
    # Verify size reduction
    print("Checking new size...")
    child.sendline("du -sh /root/snapshots")
    child.expect(['#', '$'], timeout=10)
    print(child.before.strip())

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
except Exception as e:
    print(e)
