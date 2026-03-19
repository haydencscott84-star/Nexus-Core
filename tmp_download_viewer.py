import pexpect
import sys

child = pexpect.spawn('scp -o StrictHostKeyChecking=no root@<YOUR_VPS_IP>:/root/viewer_dash_nexus.py remote_viewer_dash_nexus.py')
child.expect('password:')
child.sendline('<YOUR_VPS_PASSWORD>')
child.expect(pexpect.EOF)
print(child.before.decode('utf-8'))
