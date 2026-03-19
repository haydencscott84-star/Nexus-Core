import os
import pty
import sys
import select

HOST = "root@<YOUR_VPS_IP>"
PASSWORD = "<YOUR_VPS_PASSWORD>"

def secure_copy(local_path, remote_path):
    # Construct SCP command
    # scp -o StrictHostKeyChecking=no local_path root@HOST:remote_path
    cmd = ["scp", "-o", "StrictHostKeyChecking=no", local_path, f"{HOST}:{remote_path}"]
    
    print(f"🚀 SCP: {local_path} -> {HOST}:{remote_path}")
    
    pid, master_fd = pty.fork()
    
    if pid == 0:
        os.execvp(cmd[0], cmd)
    else:
        password_sent = False
        while True:
            r, w, e = select.select([master_fd], [], [], 0.5)
            
            if master_fd in r:
                try:
                    data = os.read(master_fd, 1024)
                    if not data: break
                    
                    sys.stdout.buffer.write(data)
                    sys.stdout.flush()
                    
                    if not password_sent and (b"password:" in data.lower() or b"Password:" in data):
                        os.write(master_fd, (PASSWORD + "\n").encode())
                        password_sent = True
                        
                except OSError:
                    break
            
            # Check if process exited
            if os.waitpid(pid, os.WNOHANG) != (0, 0):
                break
                
        os.close(master_fd)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 secure_scp.py <local_path> <remote_path>")
        sys.exit(1)
    
    secure_copy(sys.argv[1], sys.argv[2])
