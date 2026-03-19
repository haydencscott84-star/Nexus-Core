import pexpect
import sys

child = pexpect.spawn('scp -o StrictHostKeyChecking=no analyze_snapshots.py root@<YOUR_VPS_IP>:/root/')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)

child2 = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "tmux respawn-window -k -t nexus:ANALYZE_SNAPSHOTS && sleep 1 && tmux send-keys -t nexus:ANALYZE_SNAPSHOTS \'cd /root && python3 robust_wrapper.py python3 analyze_snapshots.py\' Enter && sleep 3 && tmux capture-pane -p -t nexus:ANALYZE_SNAPSHOTS -S -50"')
child2.expect('password:')
child2.sendline('<YOUR_VPS_PASSWORD>')
child2.expect(pexpect.EOF)
print(child2.before.decode('utf-8'))
