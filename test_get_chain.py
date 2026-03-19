import zmq
import json

def test_zmq():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect("tcp://127.0.0.1:5567")
    
    payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "strike": "680", "width": "5", "type": "CALL"}
    print(f"Testing GET_CHAIN with {payload}...")
    sock.send_json(payload)
    
    if sock.poll(15000):
        reply = sock.recv_json()
        if reply.get("status") == "ok":
            iv = reply.get("iv")
            ivr = reply.get("ivr")
            data = reply.get("data", [])
            print(f"SUCCESS: IV={iv}%, IVR={ivr}, Chains Fetched: {len(data)}")
            if len(data) > 0:
                print(f"FIRST FEW ROWS: {json.dumps(data[:3], indent=2)}")
            else:
                print("SERVER RETURNED EMPTY SPREADS ARRAY []!")
        else:
            print(f"ERROR REPLY: {reply}")
    else:
        print("TIMEOUT: No response from 5567.")

if __name__ == "__main__":
    test_zmq()
