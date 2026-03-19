import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

# Inserting before line 386 (approx) where type_str is defined.
# Match: type_str = "PUT"
# Insert fix before it.

cmd = r"""sed -i '/type_str = "PUT"/i \                # [FIX] Override\\n                try:\\n                    if "C" in short_sym.split(" ")[-1]: is_put = False\\n                    elif "P" in short_sym.split(" ")[-1]: is_put = True\\n                except: pass' /root/nexus_spreads.py"""

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host} "{cmd}"', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(pexpect.EOF, timeout=30)
    print("Output:")
    print(child.before)
    
except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
