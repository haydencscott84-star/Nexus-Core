import base64
import pexpect
import sys
import time

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

local_file = 'local_fix_script.py'
remote_b64 = '/root/apply_fix.b64'
remote_target = '/root/apply_fix.py'

print(f"Encoding {local_file}...")
with open(local_file, 'rb') as f:
    data = f.read()
    b64_data = base64.b64encode(data).decode('utf-8')

# Chunk size
chunk_size = 1000
chunks = [b64_data[i:i+chunk_size] for i in range(0, len(b64_data), chunk_size)]

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    # 1. Clear old
    child.sendline(f"rm {remote_b64}")
    child.expect(['#', '$'], timeout=10)
    
    # 2. Upload chunks
    print(f"Sending {len(chunks)} chunks...")
    for idx, chunk in enumerate(chunks):
        cmd = f"echo -n '{chunk}' >> {remote_b64}"
        child.sendline(cmd)
        # Wait for prompt every few chunks to prevent buffer overflow/lag
        if idx % 10 == 0:
            child.expect(['#', '$'], timeout=10)
    
    child.expect(['#', '$'], timeout=10)
    
    # 3. Decode
    child.sendline(f"base64 -d {remote_b64} > {remote_target}")
    child.expect(['#', '$'], timeout=10)
    
    # 4. Execute
    child.sendline(f"python3 {remote_target}")
    child.expect(['#', '$'], timeout=10)
    print("--- EXECUTION OUTPUT ---")
    print(child.before)

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
except Exception as e:
    print(f"Error: {e}")
