import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

commands = [
    "du -sh /root/snapshots",
    "grep -n 'class StrategicHUD' /root/analyze_snapshots.py",
    # Read the class definition to find loading logic
    "sed -n '/class StrategicHUD/,/def compose/p' /root/analyze_snapshots.py"
]

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
        # Filter output to remove command echo if present, or just print
        print(child.before.strip())
    except Exception as e:
        print(f"Failed: {e}")
