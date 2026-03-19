import pexpect
import sys

host = "45.77.204.159"
user = "root"
password = r"$K8w$AF%f={*@{F?"

remote_script = """
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f: content = f.read()

    target = 'is_put = spread_data.get("is_put", False)'
    
    # We insert the fix immediately after
    fix_code = '''is_put = spread_data.get("is_put", False)
                
                # [FIX] Override based on Symbol ID (Source of Truth)
                try:
                    short_id = short_sym.split(' ')[-1]
                    if "C" in short_id and "P" not in short_id: is_put = False
                    elif "P" in short_id and "C" not in short_id: is_put = True
                except: pass'''
    
    if target in content and "[FIX] Override" not in content:
        content = content.replace(target, fix_code)
        with open(path, 'w') as f: f.write(content)
        print("PATCH_SUCCESS")
    else:
        print("PATCH_SKIPPED")
        if "[FIX] Override" in content: print("ALREADY_PATCHED")

except Exception as e:
    print(e)
"""

print(f"Connecting to {user}@{host}...")
child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')

try:
    i = child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
    if i == 1:
        child.sendline('yes')
        child.expect('password:')
    
    child.sendline(password)
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("cat <<EOF > patch_spreads.py")
    child.sendline(remote_script)
    child.sendline("EOF")
    child.expect(['#', '$'], timeout=10)
    
    child.sendline("python3 patch_spreads.py")
    child.expect(['#', '$'], timeout=10)
    print("Output:")
    print(child.before)
    
    child.sendline("rm patch_spreads.py")

except pexpect.TIMEOUT:
    print("Timeout")
    print(child.before)
