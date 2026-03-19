import pexpect
import sys

# Send 'reset', Enter to the pane and launch it cleanly
child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "tmux send-keys -t nexus:ANALYZE_SNAPSHOTS C-c reset Enter && sleep 2 && tmux send-keys -t nexus:ANALYZE_SNAPSHOTS \'python3 robust_wrapper.py python3 analyze_snapshots.py\' Enter && sleep 2 && tmux capture-pane -p -t nexus:ANALYZE_SNAPSHOTS -S -50"')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
