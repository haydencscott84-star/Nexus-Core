
import zmq
import json
import datetime

ZMQ_PORT_ACCOUNT = 5566

def listen_account():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.SUB)
    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_ACCOUNT}")
    sock.subscribe(b"") # Subscribe to all
    
    print(f"Listening on Account Stream {ZMQ_PORT_ACCOUNT}...")
    
    start = datetime.datetime.now()
    while (datetime.datetime.now() - start).seconds < 15: # Listen for 15s
        if sock.poll(1000):
            topic, msg = sock.recv_multipart()
            try:
                data = json.loads(msg)
                print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] TOPIC: {topic.decode()}")
                
                positions = data.get("positions", [])
                equity = data.get("total_account_value", "N/A")
                
                print(f"Account: {data.get('account_id', 'Unknown')}")
                print(f"Equity: {equity}")
                print(f"Position Count: {len(positions)}")
                
                if positions:
                    print("--- POSITIONS ---")
                    for p in positions:
                        print(f"Sym: {p.get('Symbol')} | Qty: {p.get('Quantity')} | P/L: {p.get('UnrealizedProfitLoss')}")
            except Exception as e:
                print(f"Error parsing: {e}")
        else:
            print(".", end="", flush=True)

if __name__ == "__main__":
    listen_account()
