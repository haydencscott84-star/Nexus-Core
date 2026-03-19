import sys
import os
import json
import time
from nexus_copycat_bot import WhaleHunter, parse_log_line

# Mock Config
LOG_FILE_PATHS = ["logs/test_sweeps_v1.log", "logs/test_sweeps_v2.log"]

def create_test_logs():
    os.makedirs("logs", exist_ok=True)
    for p in LOG_FILE_PATHS:
        with open(p, "w") as f: f.write("")

def append_trade(path, trade):
    with open(path, "a") as f:
        f.write(json.dumps(trade) + "\n")
    print(f"   -> Appended to {path}: {trade['ticker']} ${trade['premium']}")

def run_dual_test():
    print("🚀 Starting Dual-Source Shadow Bot Test...")
    create_test_logs()
    hunter = WhaleHunter()
    
    # Simulate V1 Trade
    t1 = {"ticker": "SPY", "expiration": "2026-06-20", "strike": 550, "type": "CALL", "premium": 1_500_000, "volume": 1000, "open_interest": 500, "executed_at": time.time()}
    append_trade(LOG_FILE_PATHS[0], t1)
    
    # Simulate V2 Trade (Same Cluster)
    t2 = {"ticker": "SPY", "expiration": "2026-06-20", "strike": 555, "type": "CALL", "premium": 2_000_000, "volume": 1000, "open_interest": 500, "executed_at": time.time()}
    append_trade(LOG_FILE_PATHS[1], t2)
    
    print("   -> Reading logs...")
    
    # Mock Polling Logic
    handles = {}
    for p in LOG_FILE_PATHS:
        f = open(p, 'r') # Start from beginning for test
        handles[p] = f
        
    found_signal = False
    for p, f in handles.items():
        lines = f.readlines()
        for line in lines:
            trade = parse_log_line(line)
            if trade:
                sig = hunter.ingest_trade(trade)
                if sig:
                    print(f"   ✅ WHALE DETECTED from {p}: {sig['notional']/1e6:.1f}M")
                    found_signal = True
                    
    if found_signal:
        print("✅ Dual-Source Test Passed!")
    else:
        print("❌ Failed to detect signal across files.")

if __name__ == "__main__":
    run_dual_test()
