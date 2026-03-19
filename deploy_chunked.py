
# CHUNKED DEPLOYMENT SCRIPT
# Robustly sends files to server even if large.

import os, base64, subprocess, time

FILES = {
    "nexus_spreads.py": "/root/nexus_spreads.py",
    "nexus_debit.py": "/root/nexus_debit.py"
}

SSH_HELPER = "/Users/haydencscott/.gemini/antigravity/brain/231c1b02-d1e3-4ef1-bbd4-e1edd210a9bf/ssh_helper.exp"
SSH_PASS = "$K8w$AF%f={*@{F?"

def deploy_file(local_path, remote_path):
    print(f"Deploying {local_path} -> {remote_path}...")
    
    with open(local_path, "rb") as f:
        data = f.read()
        
    b64_data = base64.b64encode(data).decode('utf-8')
    
    # 1. Clear remote temp file
    temp_remote = remote_path + ".b64"
    cmd_clear = f"rm -f {temp_remote}"
    run_ssh(cmd_clear)
    
    # 2. Chunk processing
    CHUNK_SIZE = 4000 # Keep well under safe arg limits
    total = len(b64_data)
    
    for i in range(0, total, CHUNK_SIZE):
        chunk = b64_data[i:i+CHUNK_SIZE]
        # Build command: echo -n "CHUNK" >> temp
        cmd_append = f"echo -n \"{chunk}\" >> {temp_remote}"
        run_ssh(cmd_append)
        print(f"  Sent chunk {i}/{total}...")
        
    # 3. Decode
    cmd_decode = f"base64 -d {temp_remote} > {remote_path}"
    run_ssh(cmd_decode)
    print(f"Decoded {remote_path}.")

def run_ssh(remote_cmd):
    # Construct the exp command
    # Env var for pass
    env = os.environ.copy()
    env["SSH_PASS"] = SSH_PASS
    
    # We must escape quotes in remote_cmd for the helper logic if needed, 
    # but the helper typically wraps args.
    # The helper sends the arg as a command buffer.
    # Warning: "echo" needs escaped quotes inside? 
    # Yes, if we pass echo "foo", it works.
    
    subprocess.run([SSH_HELPER, remote_cmd], env=env, check=True)

if __name__ == "__main__":
    for local, remote in FILES.items():
        if os.path.exists(local):
            deploy_file(local, remote)
        else:
            print(f"Missing local file: {local}")
            
    # Trigger restart
    print("Restarting Nexus...")
    run_ssh("tmux kill-session -t nexus; sleep 2; ./launch_cockpit.sh")
