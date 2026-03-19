import zmq
import json
import time

ZMQ_PORT = 9999

def main():
    print("[*] Starting Test Script (Dry Run)...")
    
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    
    # Bind to the port (Act as Publisher)
    print(f"[*] Binding to tcp://*:{ZMQ_PORT}...")
    try:
        socket.bind(f"tcp://*:{ZMQ_PORT}")
    except zmq.ZMQError as e:
        print(f"[!] Could not bind to port {ZMQ_PORT}: {e}")
        print("[!] Is uw_nexus.py already running?")
        exit(1)
    
    # Allow time for connection to be established (Subscriber needs time to sync)
    time.sleep(1)
    
    print("[*] Sending dummy messages...")
    
    # 1. TEST Message
    msg_test = {"type": "TEST"}
    print(f"[<] Sending: {msg_test}")
    socket.send_json(msg_test)
    time.sleep(1)
    
    # 2. Bullish Whale (Z-Score -16.0)
    msg_bullish = {"type": "ALERT", "z_score": -16.0}
    print(f"[<] Sending: {msg_bullish}")
    socket.send_json(msg_bullish)
    time.sleep(1)
    
    # 3. Bearish Whale (Z-Score +16.0)
    msg_bearish = {"type": "ALERT", "z_score": 16.0}
    print(f"[<] Sending: {msg_bearish}")
    socket.send_json(msg_bearish)
    time.sleep(1)
    
    print("[*] Done. Check your Discord channel.")

if __name__ == "__main__":
    main()
