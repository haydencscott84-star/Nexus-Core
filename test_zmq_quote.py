import zmq
import json

context = zmq.Context()
sock = context.socket(zmq.REQ)
sock.connect("tcp://127.0.0.1:5567")

payload = {"cmd": "GET_MULTI_QUOTE", "symbols": ["SPY", "QQQ"]}
sock.send_json(payload)

if sock.poll(5000):
    reply = sock.recv_json()
    print("REPLY:", json.dumps(reply, indent=2))
else:
    print("TIMEOUT")
