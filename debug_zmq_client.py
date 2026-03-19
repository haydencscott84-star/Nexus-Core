import zmq
import json
import time

ZMQ_PORT_EXEC = 5567
ACCOUNT_ID = "210VGM01"

def test_zmq():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(f"tcp://localhost:{ZMQ_PORT_EXEC}")
    
    print(f"Sending Request for {ACCOUNT_ID}...")
    start = time.time()
    
    sock.send_json({"cmd": "GET_POSITIONS", "account_id": ACCOUNT_ID})
    
    # Simple blocking poll
    if sock.poll(15000): # 15s timeout
        msg = sock.recv_json()
        elapsed = time.time() - start
        print(f"✅ RECEIVED REPLY in {elapsed:.2f}s")
        print(f"DATA: {msg}")
    else:
        elapsed = time.time() - start
        print(f"❌ TIMEOUT after {elapsed:.2f}s")
        
    sock.close()
    ctx.term()

if __name__ == "__main__":
    test_zmq()
