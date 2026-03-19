import pexpect
import sys
import time

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

local_file = 'analyze_snapshots_downloaded.py'
remote_file = '/root/analyze_snapshots.py'

print(f"Reading local file {local_file}...")
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
    
    # Start cat
    child.sendline(f"cat > {remote_file} << 'EOF_MARKER'")
    
    lines = content.split('\n')
    for idx, line in enumerate(lines):
        child.sendline(line)
        if idx % 100 == 0:
             time.sleep(0.05)
             print(f"Sent {idx}/{len(lines)} lines...")
             
    child.sendline("EOF_MARKER")
    child.expect(['#', '$'], timeout=30)
    print("Upload complete.")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
except Exception as e:
    print(e)
