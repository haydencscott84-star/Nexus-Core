import zmq
import sys
import json

# EXACT SYMBOLS FROM USER'S SPREAD
# Credit Put: 672/667 Exp Jan 30
# Symbol Format: SPY [YYMMDD]P[Strike]
# 30 Jan 2026 -> 260130
SHORT_SYM = "SPY 260130P672"
LONG_SYM = "SPY 260130P667"
QTY = 10
SIDE = "SELL" # Original Side (Credit)

def send_kill_command():
    context = zmq.Context()
    sock = context.socket(zmq.REQ)
    sock.connect("tcp://127.0.0.1:5567")

    print(f"🔥 CONNECTING TO ZMQ (5567)...")
    
    payload = {
        "cmd": "CLOSE_SPREAD",
        "short_sym": SHORT_SYM,
        "long_sym": LONG_SYM,
        "qty": QTY,
        "side": SIDE
    }
    
    print(f"🚀 SENDING PAYLOAD: {json.dumps(payload, indent=2)}")
    sock.send_json(payload)
    
    print("⏳ WAITING FOR REPLY...")
    socks = dict(zmq.Poller().poll(10000)) # 10s timeout
    
    if sock in socks:
        reply = sock.recv_json()
        print(f"✅ REPLY: {reply}")
    else:
        print("❌ TIMEOUT: No reply from Backend.")
        
if __name__ == "__main__":
    send_kill_command()
