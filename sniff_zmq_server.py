import zmq
import json
import datetime

context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect("tcp://127.0.0.1:5566")
socket.subscribe(b"A")

print("🎧 STARTING ZMQ SNIFFER ON PORT 5566...")

while True:
    try:
        topic, msg = socket.recv_multipart()
        data = json.loads(msg)
        t = datetime.datetime.now().strftime("%H:%M:%S")
        
        eq = data.get("total_account_value", 0)
        pos_count = len(data.get("positions", []))
        
        print(f"[{t}] EQ: ${eq} | POS: {pos_count}")
        if pos_count > 0:
            print(f"   -> Sample: {data['positions'][0].get('Symbol')}")
            
    except KeyboardInterrupt:
        break
    except Exception as e:
        print(f"ERROR: {e}")
