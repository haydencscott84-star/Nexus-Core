
import zmq
import json
import time

ZMQ_PORT_EXEC = 5567

def test_fetch():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
    
    # Simulate Nexus Debit Request
    payload = {
        "cmd": "GET_CHAIN",
        "ticker": "SPY",
        "type": "CALL",
        "width": 30,
        "raw": True,
        "price": 682.00
    }
    
    print(f"Sending Payload: {payload}")
    sock.send_json(payload)
    
    if sock.poll(10000): 
        reply = sock.recv_json()
        if reply.get("status") == "ok":
            data = reply.get("data", [])
            print(f"Received {len(data)} raw option items (Backend Optimized).")
            
            # Count Valid Deltas to confirm we have ENOUGH data
            valid = 0
            for item in data:
                d = float(item.get("delta", 0))
                if 0.65 <= abs(d) <= 0.80:
                    valid += 1
            print(f"Valid Candidates (Delta 0.65-0.80): {valid}")
            
        else:
            print(f"Error: {reply.get('msg')}")
    else:
        print("Timeout.")

if __name__ == "__main__":
    test_fetch()
