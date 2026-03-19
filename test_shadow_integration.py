import sys
import os
import json
import time
import threading
from nexus_copycat_bot import WhaleHunter, parse_log_line

# Mock Config
TEST_LOG_FILE = "logs/test_sweeps_v2.log"

def create_test_log():
    os.makedirs("logs", exist_ok=True)
    with open(TEST_LOG_FILE, "w") as f:
        f.write("") # Clear it

def append_trade_to_log(trade):
    with open(TEST_LOG_FILE, "a") as f:
        f.write(json.dumps(trade) + "\n")
    print(f"   -> Appended trade: {trade['ticker']} ${trade['premium']}")

def run_integration_test():
    print("🚀 Starting Shadow Bot Integration Test...")
    
    # 1. Setup
    create_test_log()
    hunter = WhaleHunter()
    
    # 2. Simulate Producer (Sweeps V2) writing to log
    # We need 3 trades to form a cluster > $3M (since we tuned it to $3M)
    trades = [
        {"ticker": "SPY", "expiration": "2026-06-20", "strike": 550, "type": "CALL", "premium": 1_500_000, "volume": 1000, "open_interest": 500, "executed_at": time.time()},
        {"ticker": "SPY", "expiration": "2026-06-20", "strike": 555, "type": "CALL", "premium": 1_500_000, "volume": 1000, "open_interest": 500, "executed_at": time.time()},
        {"ticker": "SPY", "expiration": "2026-06-20", "strike": 560, "type": "CALL", "premium": 1_500_000, "volume": 1000, "open_interest": 500, "executed_at": time.time()}
    ]
    
    print("   -> Simulating log stream...")
    for t in trades:
        append_trade_to_log(t)
        time.sleep(0.1)
        
    # 3. Simulate Consumer (Shadow Bot) reading log
    print("   -> Reading log...")
    with open(TEST_LOG_FILE, "r") as f:
        lines = f.readlines()
        for line in lines:
            trade = parse_log_line(line)
            if trade:
                sig = hunter.ingest_trade(trade)
                if sig:
                    print(f"   ✅ WHALE DETECTED: {sig['notional']/1e6:.1f}M {sig['option_type']} on {sig['expiration']}")
                    return
    
    print("   ❌ NO SIGNAL DETECTED. Integration failed.")

if __name__ == "__main__":
    run_integration_test()
