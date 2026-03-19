import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host} "cat /root/nexus_spreads.py"', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    # Match EOF loop to capture all output
    child.expect(pexpect.EOF, timeout=30)
    
    content = child.before
    # Filter out login banner if present (usually not in 'cat' output if command is passed to ssh)
    # But clean it just in case.
    # Actually, with 'ssh cmd', child.before contains just the output + maybe prompts if TTY is weird.
    # Usually it works.
    
    with open('nexus_spreads_downloaded.py', 'w') as f:
        f.write(content)
        
    print(f"Downloaded {len(content)} chars.")
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
