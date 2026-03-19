import zmq
import json
import time

PORT = 5567
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect(f"tcp://127.0.0.1:{PORT}")
sock.setsockopt(zmq.LINGER, 0)
sock.setsockopt(zmq.RCVTIMEO, 2000) # 2s timeout

print(f"Connecting to {PORT}...")
payload = {"cmd": "GET_POSITIONS"} # Valid command
print(f"Sending: {payload}")

try:
    sock.send_json(payload)
    print("Waiting for reply...")
    reply = sock.recv_json()
    print(f"Reply: {reply}")
except zmq.Again:
    print("TIMEOUT: Backend did not reply in 2s.")
except Exception as e:
    print(f"ERROR: {e}")
finally:
    sock.close()
    ctx.term()
