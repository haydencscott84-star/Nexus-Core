import pexpect
import sys

child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "tail -n 10 /root/snapshots_spy/$(ls -t /root/snapshots_spy | head -n 1)"')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
