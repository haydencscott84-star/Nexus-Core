import zmq
import json
import time

ZMQ_PORT_EXEC = 5567

def verify_connectivity():
    print(f"🔌 Connecting to Nexus Execution Port ({ZMQ_PORT_EXEC})...")
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
    
    # Test Payload: Fetch Option Chain (Safe)
    payload = {
        "cmd": "GET_CHAIN",
        "ticker": "SPY",
        "strike": 665, # Arbitrary near-the-money strike
        "width": 5,
        "type": "PUT"
    }
    
    print(f"📤 Sending Test Command: {json.dumps(payload)}")
    
    try:
        sock.send_json(payload)
        
        # Wait for reply with timeout
        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        
        if poller.poll(10000): # 10s timeout
            reply = sock.recv_json()
            print("-" * 50)
            print(f"✅ REPLY RECEIVED:")
            print(json.dumps(reply, indent=2))
            print("-" * 50)
            
            if reply.get("status") == "ok":
                data = reply.get("data", [])
                print(f"🎉 SUCCESS: Received {len(data)} spread combinations.")
                print("TradeStation API is RESPONDING correctly.")
            else:
                print(f"⚠️ ERROR: API returned error status: {reply.get('msg')}")
        else:
            print("❌ TIMEOUT: No response from ts_nexus.py. Is it running?")
            
    except Exception as e:
        print(f"❌ EXCEPTION: {e}")
    finally:
        sock.close()
        ctx.term()

if __name__ == "__main__":
    verify_connectivity()
