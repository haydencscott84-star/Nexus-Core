import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

commands = [
    "tmux list-windows -t nexus",
    "ls -lh /root/nexus_history.json",
    "ls -lhd /root/snapshots",
    "du -sh /root/snapshots",
    "tmux capture-pane -pt nexus:8 -S -100",
    "ps aux | grep analyze"
]

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    for cmd in commands:
        print(f"--- Running: {cmd} ---")
        child.sendline(cmd)
        child.expect(['#', '$'], timeout=20) # Increased timeout
        print(child.before.strip())

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
except Exception as e:
    print(e)
