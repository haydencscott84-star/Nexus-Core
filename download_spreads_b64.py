import pexpect
import sys
import base64

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
    
    # Use base64 to avoid shell metacharacter issues
    child.sendline(f"base64 {remote_path}")
    child.expect(['#', '$'], timeout=60)
    
    raw_output = child.before
    # Filter out the command itself
    if f"base64 {remote_path}" in raw_output:
        raw_output = raw_output.split(f"base64 {remote_path}")[1]
        
    # Clean up whitespace/newlines
    b64_content = raw_output.strip().replace('\r\n', '').replace('\n', '')
    
    try:
        decoded = base64.b64decode(b64_content)
        with open(local_path, "wb") as f:
            f.write(decoded)
        print(f"Downloaded {len(decoded)} bytes to {local_path}")
    except Exception as e:
        print(f"Base64 Decode Error: {e}")
        # print(f"Raw was: {raw_output[:100]}...")

except pexpect.TIMEOUT:
    print("Timeout")
except Exception as e:
    print(e)
