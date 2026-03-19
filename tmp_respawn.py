import pexpect
import sys

child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "tmux respawn-window -k -t nexus:ANALYZE_SNAPSHOTS && sleep 1 && tmux send-keys -t nexus:ANALYZE_SNAPSHOTS \'cd /root && python3 robust_wrapper.py python3 analyze_snapshots.py\' Enter"')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
