import zmq
import json
import datetime
import sys

port = 9999
context = zmq.Context()
socket = context.socket(zmq.SUB)
socket.connect(f"tcp://127.0.0.1:{port}")
socket.setsockopt_string(zmq.SUBSCRIBE, "")

print(f"Listening on {port}...")

while True:
    msg = socket.recv_multipart()
    topic = msg[0].decode()
    payload = json.loads(msg[1].decode())
    
    # We only care about trades for SPY/SPX to verify V2 logic
    ticker = payload.get('ticker', 'UNKNOWN')
    if ticker not in ["SPY", "SPX", "SPXW"]:
        continue
        
    ts = payload.get('executed_at') or payload.get('created_at')
    prem = payload.get('total_premium') or payload.get('premium')
    
    print(f"--- {topic} ---")
    print(f"Ticker: {ticker}")
    print(f"TS Raw: {ts}")
    print(f"Premium: {prem}")
    print(f"Payload keys: {list(payload.keys())}")
    print("-" * 20)
    sys.stdout.flush()
