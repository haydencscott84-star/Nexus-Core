import zmq
import json
import time

ZMQ_PORT_EXEC = 5567
ACCOUNT_ID = "210VGM01"

def test_dealer():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.identity = b"TEST_DEALER_1"
    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
    
    print("Sending Request via DEALER...")
    start = time.time()
    
    # Emulate REQ: Send Empty Frame + JSON
    payload = json.dumps({"cmd": "GET_POSITIONS", "account_id": ACCOUNT_ID}).encode()
    sock.send_multipart([b'', payload])
    
    if sock.poll(15000):
        frames = sock.recv_multipart()
        elapsed = time.time() - start
        print(f"✅ RECEIVED FRAMES in {elapsed:.2f}s")
        print(f"FRAMES: {frames}")
    else:
        elapsed = time.time() - start
        print(f"❌ TIMEOUT after {elapsed:.2f}s")
        
    sock.close()
    ctx.term()

if __name__ == "__main__":
    test_dealer()
