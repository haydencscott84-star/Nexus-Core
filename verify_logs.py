import zmq
import time

ZMQ_PORT_LOGS = 5572

def verify_logs():
    print(f"👂 Listening for Logs on Port {ZMQ_PORT_LOGS}...")
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_LOGS}")
    sock.subscribe(b"") # Subscribe to all
    
    start = time.time()
    count = 0
    
    while time.time() - start < 5:
        try:
            # Non-blocking check
            if sock.poll(100): # 100ms
                msg = sock.recv_string()
                print(f"📝 LOG: {msg}")
                count += 1
        except Exception as e:
            print(f"Error: {e}")
            break
            
    if count > 0:
        print(f"✅ SUCCESS: Received {count} log messages. System is ALIVE.")
    else:
        print("❌ FAILURE: No logs received in 5 seconds. System might be IDLE or HUNG.")

if __name__ == "__main__":
    verify_logs()
