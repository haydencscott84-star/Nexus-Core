import sys
import site
sys.path.append("/Users/haydenscott/Library/Python/3.13/lib/python/site-packages")

try:
    import paramiko
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "paramiko", "--user"])
    sys.path.append("/Users/haydenscott/Library/Python/3.13/lib/python/site-packages")
    import paramiko

host = '45.77.204.159'
user = 'root'
password = r'$K8w$AF%f={*@{F?'

try:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=10)
    
    sftp = client.open_sftp()
    
    # We will just print the file content directly!
    with sftp.file('/root/analyze_snapshots.py', 'r') as f:
        content = f.read().decode('utf-8')
        
    with open('/Users/haydenscott/Desktop/Local Scripts/remote_analyze.py', 'w') as f:
        f.write(content)
        
    print("DOWNLOAD OK")
    sftp.close()
    client.close()
except Exception as e:
    print("FAILED:", e)
