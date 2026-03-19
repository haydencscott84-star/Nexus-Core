import zmq
import json
import time
import datetime

# Config to match nexus_sweeps_tui_v1.py
ZMQ_PORT = 5556
TOPIC = "flow-alerts"

def main():
    print(f"[*] Starting Injector on port {ZMQ_PORT}...")
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://*:{ZMQ_PORT}") # We bind because we act as the data source (like uw_nexus.py)
    
    # Give time for nexus_sweeps_tui_v1.py to connect
    print("[*] Waiting 5s for subscribers...")
    time.sleep(5)
    
    # Create a "Whale" trade
    # High premium to trigger Z-Score
    trade = {
        "ticker": "SPX",
        "total_premium": 50_000_000.0, # $50M Premium! Should be > 4.0 Z-Score
        "total_size": 1000,
        "open_interest": 500,
        "price": 5000.0,
        "option_chain": "SPX251219C05000000", # Fake chain
        "executed_at": time.time(),
        "total_ask_side_prem": 50_000_000.0, # Buy side
        "total_bid_side_prem": 0.0,
        "underlying_price": 5000.0
    }
    
    print(f"[<] Injecting Whale Trade: {trade['total_premium']}")
    
    # Send multipart: [Topic, JSON]
    socket.send_multipart([TOPIC.encode(), json.dumps(trade).encode('utf-8')])
    
    print("[*] Injected. Check Alert Manager logs.")

if __name__ == "__main__":
    main()
