import pty
import os
import sys
import time
import select

SERVER = "root@45.77.204.159"
PASSWORD = r"$K8w$AF%f={*@{F?"
CMD = sys.argv[1] if len(sys.argv) > 1 else "ls -la"

def remote_exec(command):
    pid, fd = pty.fork()
    if pid == 0:
        # Child process
        os.execvp("ssh", ["ssh", "-o", "StrictHostKeyChecking=no", SERVER, command])
    else:
        # Parent process
        password_sent = False
        output = []
        
        while True:
            r, _, _ = select.select([fd], [], [], 10) # 10s timeout
            if not r:
                break
            
            try:
                chunk = os.read(fd, 1024).decode('utf-8', errors='ignore')
            except OSError:
                break
                
            if not chunk:
                break
                
            # print(chunk, end='') # Debug output
            output.append(chunk)
            
            if "password:" in chunk and not password_sent:
                os.write(fd, (PASSWORD + "\n").encode())
                password_sent = True
        
        full_output = "".join(output)
        # Clean up output (remove password prompt/echo)
        clean_output = full_output.replace(f"password: {PASSWORD}", "").replace("password:", "").strip()
        print(clean_output)

if __name__ == "__main__":
    remote_exec(CMD)
