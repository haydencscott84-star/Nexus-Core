import pexpect
import sys

child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "sleep 15 && tmux capture-pane -p -t nexus:ANALYZE_SNAPSHOTS -e | head -n 10"')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
