import pexpect

host = '45.77.204.159'
user = 'root'
password = r'$K8w$AF%f={*@{F?'

remote_script = """
import sys
import json
import os

path = '/root/analyze_snapshots.py'
with open(path, 'r') as f: content = f.read()

# Let's just append the push_to_supabase function if it doesn't exist.
if "def push_to_supabase" not in content:
    # Find the antigravity_dump function
    import re
    # We want to replace the body of antigravity_dump to also call push_to_supabase
    
    inject_str = '''
def get_supabase_client():
    try:
        from supabase import create_client
        import os
        from dotenv import load_dotenv
        load_dotenv('/root/.env')
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key: return None
        return create_client(url, key)
    except Exception as e:
        print(f"Supabase Client Error: {e}")
        return None

def push_to_supabase(id_val, data_dict):
    try:
        client = get_supabase_client()
        if client:
            payload = {'id': id_val, 'data': data_dict}
            response = client.table('nexus_profile').upsert(payload, on_conflict='id').execute()
            print(f"✅ [SUPABASE] Pushed {id_val}")
    except Exception as e:
        print(f"❌ [SUPABASE] Push Failed for {id_val}: {e}")
'''
    content = inject_str + "\n" + content

    # Now replace the body of antigravity_dump
    target = '''        os.replace(temp_file, filename)
        print(f"✅ [HISTORY] Wrote {filename}")'''
        
    replacement = '''        os.replace(temp_file, filename)
        print(f"✅ [HISTORY] Wrote {filename}")
        
        # Determine ID based on filename
        if 'quant' in filename.lower():
            push_to_supabase('nexus_quant', data_dictionary)
        elif 'history' in filename.lower():
            push_to_supabase('nexus_history', data_dictionary)'''

    if target in content:
        content = content.replace(target, replacement)
        with open(path, 'w') as f: f.write(content)
        print("PATCH_SUCCESS")
    else:
        print("TARGET_NOT_FOUND")
else:
    print("PATCH_ALREADY_APPLIED")
"""

child = pexpect.spawn(f'ssh {user}@{host}', encoding='utf-8')
child.expect(['password:', 'continue connecting (yes/no/[fingerprint])?'], timeout=10)
child.sendline(password)
child.expect(['#', '$'], timeout=10)

child.sendline("cat << 'EOF' > /tmp/patch_snapshots_supabase.py")
child.sendline(remote_script)
child.sendline("EOF")
child.expect(['#', '$'], timeout=10)

child.sendline("python3 /tmp/patch_snapshots_supabase.py")
child.expect(['#', '$'], timeout=10)
print(child.before)

# Restart TMUX
child.sendline('tmux send-keys -t nexus:9 C-c')
child.expect(['#', '$'], timeout=10)
child.sendline('tmux send-keys -t nexus:9 "python3 analyze_snapshots.py --headless" C-m')
child.expect(['#', '$'], timeout=10)
print("Restarted Tmux 9")
child.sendline("exit")

