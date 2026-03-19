import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_path = "/root/nexus_spreads.py"
local_path = "nexus_spreads_debug.py"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    # Use cat to dump content
    child.sendline(f"cat {remote_path}")
    child.expect(['#', '$'], timeout=30)
    
    content = child.before
    # Strip the echoed command if present (simple heuristic: split by first newline if needed, or just save all)
    # Usually 'cat ...' is echoed, then content, then prompt.
    # The 'before' captures everything up to the prompt.
    
    # Remove the command line from the start if it exists
    if f"cat {remote_path}" in content:
        content = content.split(f"cat {remote_path}")[-1]
    
    with open(local_path, "w") as f:
        f.write(content.strip())
        
    print(f"Downloaded {len(content)} bytes to {local_path}")

except pexpect.TIMEOUT:
    print("Timeout")
except Exception as e:
    print(e)
