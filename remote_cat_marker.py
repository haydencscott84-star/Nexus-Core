import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_path = "/root/nexus_spreads.py"
local_path = "nexus_spreads_full.py"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    # Use a unique marker
    marker = "___FILE_END_MARKER___"
    child.sendline(f"cat {remote_path}; echo '{marker}'")
    
    # Expect the marker, not the prompt immediately
    child.expect(marker, timeout=60)
    
    content = child.before
    
    # Filter out the command line echo
    if f"cat {remote_path}" in content:
        content = content.split(f"echo '{marker}'")[0] # The echo command might be in buffer
        # actually, splitting by the command is trickier.
        # Let's simple split by newlines and remove the first/last few if needed.
        pass
        
    # Python pexpect 'before' includes everything up to the match.
    # It might include the echoed command line at the top.
    
    with open(local_path, "w") as f:
        f.write(content)
        
    print(f"Downloaded {len(content)} bytes to {local_path}")

except pexpect.TIMEOUT:
    print("Timeout")
    # Save what we got
    with open(local_path, "w") as f:
        f.write(child.before)
except Exception as e:
    print(e)
