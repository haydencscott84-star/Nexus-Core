import base64
import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"
if len(sys.argv) < 2:
    print("Usage: python3 robust_upload.py <filename>")
    sys.exit(1)

filename = sys.argv[1]
local_file = filename
remote_b64 = f'/root/{filename}.b64'
remote_target = f'/root/{filename}'

print("Reading and encoding...")
with open(local_file, 'rb') as f:
    data = f.read()
    b64_data = base64.b64encode(data).decode('utf-8')

# Chunk size for safe echo
# Chunk size for safe echo
chunk_size = 500
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
    
    print("Clearing old b64...")
    child.sendline(f"rm {remote_b64}")
    child.expect(['#', '$'], timeout=10)
    
    print(f"Sending {len(chunks)} chunks...")
    for idx, chunk in enumerate(chunks):
        cmd = f"echo -n '{chunk}' >> {remote_b64}"
        child.sendline(cmd)
        # Verify prompt returned? No, just send fast but safely.
        # Periodic expect is safer
        if idx % 5 == 0:
            child.expect(['#', '$'], timeout=60)
            print(f"Sent chunk {idx}")
    
    # Final expect
    child.expect(['#', '$'], timeout=10)
    
    print("Decoding...")
    child.sendline(f"base64 -d {remote_b64} > {remote_target}")
    child.expect(['#', '$'], timeout=10)
    
    print("Complete.")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
except Exception as e:
    print(e)
