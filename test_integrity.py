import json
import os
import time
import shutil
from market_bridge import BridgeEngine

def test_persistence():
    print("🧪 STARTING INTEGRITY TEST (3 CYCLES)...")
    
    # Setup: Ensure we have a valid portfolio file to start
    port_file = "nexus_portfolio.json"
    backup_file = "nexus_portfolio.bak"
    
    if os.path.exists(port_file):
        shutil.copy(port_file, backup_file)
    else:
        # Create dummy if not exists
        with open(port_file, "w") as f:
            json.dump({"active_trade": {"ticker": "TEST_SPY", "qty": 1}}, f)
            
    engine = BridgeEngine()
    
    # CYCLE 1: Normal Operation
    print("\n--- CYCLE 1: NORMAL ---")
    engine.run_cycle()
    with open("market_state.json", "r") as f:
        state = json.load(f)
    ticker = state.get("active_position", {}).get("active_trade", {}).get("ticker")
    print(f"✅ Cycle 1 Ticker: {ticker}")
    if ticker != "TEST_SPY" and ticker != "SPY": print("❌ FAIL: Ticker missing in Cycle 1")

    # CYCLE 2: Simulated Failure (Delete Source)
    print("\n--- CYCLE 2: SIMULATED FAILURE (Source Deleted) ---")
    if os.path.exists(port_file):
        os.remove(port_file)
        
    engine.run_cycle() # Should use memory
    with open("market_state.json", "r") as f:
        state = json.load(f)
    
    ticker = state.get("active_position", {}).get("active_trade", {}).get("ticker")
    quality = state.get("data_quality", {}).get("portfolio", {})
    
    print(f"✅ Cycle 2 Ticker (Persisted): {ticker}")
    print(f"ℹ️  Cycle 2 Status: {quality.get('status')} (Expected: PERSISTED/STALE)")
    
    if not ticker:
        print("❌ FAIL: Position disappeared in Cycle 2!")
    else:
        print("✅ PASS: Position persisted despite missing file.")

    # CYCLE 3: Recovery
    print("\n--- CYCLE 3: RECOVERY ---")
    # Restore file
    if os.path.exists(backup_file):
        shutil.copy(backup_file, port_file)
        
    engine.run_cycle()
    with open("market_state.json", "r") as f:
        state = json.load(f)
    ticker = state.get("active_position", {}).get("active_trade", {}).get("ticker")
    quality = state.get("data_quality", {}).get("portfolio", {})
    
    print(f"✅ Cycle 3 Ticker: {ticker}")
    print(f"ℹ️  Cycle 3 Status: {quality.get('status')} (Expected: ONLINE)")
    
    # Cleanup
    if os.path.exists(backup_file):
        os.remove(backup_file) # Keep port_file as it was restored

    print("\n🧪 TEST COMPLETE.")

if __name__ == "__main__":
    test_persistence()
