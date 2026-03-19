import pexpect
import sys

def check_services():
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "tmux ls && echo \'---\' && ps aux | grep -E \'viewer_dash_nexus|analyze_snapshots\' | grep -v grep"')
    child.expect('password:')
    child.sendline('<YOUR_VPS_PASSWORD>')
    child.expect(pexpect.EOF)
    print(child.before.decode('utf-8'))

if __name__ == '__main__':
    check_services()
