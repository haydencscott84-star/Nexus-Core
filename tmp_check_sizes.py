import pexpect
import sys

child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "ls -lh /root/snapshots_spy | tail -n 5 && ls -lh /root/snapshots | tail -n 5"')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
