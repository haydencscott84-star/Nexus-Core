import os
import pty
import sys
import select

HOST = "root@45.77.204.159"
PASSWORD = "$K8w$AF%f={*@{F?"

def check():
    print("Checking active sessions...")
    cmd = ["ssh", "-o", "StrictHostKeyChecking=no", HOST, "tmux list-sessions"]
    
    pid, master_fd = pty.fork()
    if pid == 0:
        os.execvp(cmd[0], cmd)
    else:
        pw_sent = False
        while True:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if master_fd in r:
                try:
                    data = os.read(master_fd, 1024)
                    if not data: break
                    sys.stdout.buffer.write(data)
                    if not pw_sent and (b"password:" in data.lower() or b"Password:" in data):
                        os.write(master_fd, (PASSWORD + "\n").encode())
                        pw_sent = True
                except OSError: break
            if os.waitpid(pid, os.WNOHANG) != (0, 0): break
        os.close(master_fd)

if __name__ == "__main__":
    check()
