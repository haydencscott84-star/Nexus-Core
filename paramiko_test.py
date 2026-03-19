#!/usr/bin/env python3
import os
import paramiko
import sys

host = "<YOUR_VPS_IP>"
user = "root"
password = "<YOUR_VPS_PASSWORD>"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(host, username=user, password=password, timeout=10)
    
    # Run unbuffered
    stdin, stdout, stderr = client.exec_command("python3 -u /root/remote_broad_market_streamer.py", timeout=5)
    
    try:
        out = stdout.read().decode()
        err = stderr.read().decode()
        status = stdout.channel.recv_exit_status()
        print(f"EXIT: {status}")
        print(f"STDOUT: {out}")
        print(f"STDERR: {err}")
    except Exception as e:
        print(f"Exec Error (Might just be timeout on infinite loop): {e}")
        
finally:
    client.close()
