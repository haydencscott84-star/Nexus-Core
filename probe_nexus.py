import zmq
import json

context = zmq.Context()
sock = context.socket(zmq.REQ)
sock.connect("tcp://127.0.0.1:5567")

sock.send_json({"cmd": "GET_MANAGED_SPREADS"})
poll = sock.poll(2000)
if poll:
    reply = sock.recv_json()
    print(json.dumps(reply, indent=2))
else:
    print("No response from Nexus Engine.")
