import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

commands = [
    "ls -lh /root/nexus_history.json",
    "du -sh /root/snapshots",
    "ps aux | grep analyze"
]

for cmd in commands:
    print(f"--- Running: {cmd} ---")
    try:
        # direct exec
        child = pexpect.spawn(f'ssh {user}@{host} "{cmd}"', encoding='utf-8')
        i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
        if i == 1:
            child.sendline('yes')
            child.expect('password:')
        
        child.sendline(password)
        child.expect(pexpect.EOF, timeout=20)
        print(child.before.strip())
    except Exception as e:
        print(f"Failed: {e}")

# Also read relevant parts of analyze_snapshots.py
print("--- Reading analyze_snapshots.py ---")
try:
    cmd_read = "sed -n '/def on_mount/,/def compose/p' /root/analyze_snapshots.py"
    child = pexpect.spawn(f'ssh {user}@{host} "{cmd_read}"', encoding='utf-8')
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(pexpect.EOF, timeout=20)
    print(child.before.strip())
except Exception as e:
    print(e)
