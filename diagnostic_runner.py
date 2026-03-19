import os
import pty
import sys
import select
import time

# CONFIG
HOST = "root@45.77.204.159"
PASSWORD = "$K8w$AF%f={*@{F?"

DIAG_COMMANDS = [
    "echo '--- 1. SYSTEM CHECK ---'",
    "uname -a",
    "which tmux",
    "python3 --version",
    
    "echo '--- 2. FILE CHECK ---'",
    "ls -l launch_cockpit.sh viewer_dash_nexus.py",
    
    "echo '--- 3. PERMISSION FIX ---'",
    "chmod +x launch_cockpit.sh",
    
    "echo '--- 4. LAUNCH ATTEMPT ---'",
    "./launch_cockpit.sh",
    "sleep 2",
    
    "echo '--- 5. SESSION CHECK ---'",
    "tmux list-sessions",
    
    "echo '--- 6. LOG CHECK ---'",
    "tail -n 10 viewer_debug.log 2>/dev/null || echo 'No debug log found'"
]

def run_diagnostics():
    print(f"\n🔍 RUNNING DIAGNOSTICS ON {HOST}...")
    
    # Construct huge one-liner or run sequentially? 
    # Better to run as one shell session so state persists (like env vars if enabled, though ssh is non-interactive usually)
    # But for 'launch_cockpit.sh' which daemonizes, it should be fine.
    
    remote_cmd = "; ".join(DIAG_COMMANDS)
    cmd_list = ["ssh", "-o", "StrictHostKeyChecking=no", HOST, remote_cmd]
    
    pid, master_fd = pty.fork()
    
    if pid == 0:
        os.execvp(cmd_list[0], cmd_list)
    else:
        password_sent = False
        output_buffer = b""
        
        while True:
            r, w, e = select.select([master_fd], [], [], 0.5)
            
            if master_fd in r:
                try:
                    data = os.read(master_fd, 1024)
                    if not data: break
                    
                    sys.stdout.buffer.write(data)
                    output_buffer += data
                    
                    if not password_sent and (b"password:" in data.lower() or b"Password:" in data):
                        os.write(master_fd, (PASSWORD + "\n").encode())
                        password_sent = True
                        
                except OSError:
                    break
            
            if os.waitpid(pid, os.WNOHANG) != (0, 0):
                break
                
        os.close(master_fd)

if __name__ == "__main__":
    run_diagnostics()
