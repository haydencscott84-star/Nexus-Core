import pexpect

def launch():
    commands = [
        "tmux new-window -t nexus:9 -n ANALYZE_SNAPSHOTS 'cd /root && python3 robust_wrapper.py python3 analyze_snapshots.py; exec bash'",
        "tmux new-window -t nexus:15 -n VIEWER_DASH 'cd /root && python3 robust_wrapper.py python3 viewer_dash_nexus.py; exec bash'"
    ]
    
    cmd_str = " ; ".join(commands)
    
    child = pexpect.spawn(f'ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "{cmd_str}"')
    child.expect('password:')
    child.sendline('<YOUR_VPS_PASSWORD>')
    child.expect(pexpect.EOF)
    print("Launch output:", child.before.decode('utf-8'))

    # Verify windows are created
    child = pexpect.spawn('ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "tmux list-windows -t nexus | grep -E \'9:|15:\'"')
    child.expect('password:')
    child.sendline('<YOUR_VPS_PASSWORD>')
    child.expect(pexpect.EOF)
    print("Verification output:", child.before.decode('utf-8'))

if __name__ == '__main__':
    launch()
