import pexpect
import time

def get_logs():
    time.sleep(2) # Give it a second to run
    target_panes = ['nexus:9', 'nexus:15']
    command = " ; ".join([f"echo '--- Logs for {p} ---' ; tmux capture-pane -p -t {p} -S -20" for p in target_panes])
    
    child = pexpect.spawn(f'ssh -o StrictHostKeyChecking=no root@<YOUR_VPS_IP> "{command}"')
    child.expect('password:')
    child.sendline('<YOUR_VPS_PASSWORD>')
    child.expect(pexpect.EOF)
    print("--- LOGS ---")
    print(child.before.decode('utf-8'))

if __name__ == '__main__':
    get_logs()
