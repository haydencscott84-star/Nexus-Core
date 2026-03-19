import pexpect
import sys
import os

HOST = "root@<YOUR_VPS_IP>"
PASSWORD = "<YOUR_VPS_PASSWORD>"

def secure_download(remote_path, local_path):
    cmd = f"scp {HOST}:{remote_path} {local_path}"
    print(f"🚀 SCP DOWNLOAD: {remote_path} -> {local_path}")
    
    try:
        child = pexpect.spawn(cmd)
        
        # Expect loop
        while True:
            i = child.expect(["password:", "yes/no", pexpect.EOF, pexpect.TIMEOUT], timeout=30)
            if i == 0:
                child.sendline(PASSWORD)
            elif i == 1:
                child.sendline("yes")
            elif i == 2:
                break # EOF = Done
            elif i == 3:
                print("❌ TIMEOUT")
                break
                
        print("✅ Download Complete")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 download_scp.py <remote_path> <local_path>")
        sys.exit(1)
        
    secure_download(sys.argv[1], sys.argv[2])
