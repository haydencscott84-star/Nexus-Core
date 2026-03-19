import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# Read from compose onwards
cmd = "sed -n '/def compose/,/def on_mount/p' /root/analyze_snapshots.py"
cmd2 = "sed -n '/def on_mount/,/def init_tables/p' /root/analyze_snapshots.py"
# Also search for 'glob' or 'listdir' usage
cmd3 = "grep -nC 5 'glob' /root/analyze_snapshots.py"

commands = [cmd, cmd2, cmd3]

for cmd in commands:
    print(f"--- Running: {cmd} ---")
    try:
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
