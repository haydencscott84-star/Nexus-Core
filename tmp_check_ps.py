import pexpect
import sys

child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "ps aux | grep analyze_snapshots"')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
