# Verify Alert Sync
# Simulates ts_nexus.py writing to active_targets.json and alert_manager.py reading it.

import json
import time
import os

TARGET_FILE = "active_targets.json"

def test_sync():
    print("--- Testing Alert Sync ---")
    
    # 1. Simulate ts_nexus.py writing targets
    fake_registry = {
        "SPY 250116P710": {
            "type": "SPREAD",
            "stop_trigger": 595.50,
            "qty": 1,
            "armed": True
        },
        "SPY": {
            "type": "STOCK",
            "stop": 590.00,
            "take": 610.00,
            "armed": True
        }
    }
    
    print(f"Writing to {TARGET_FILE}...")
    with open(TARGET_FILE, "w") as f:
        json.dump(fake_registry, f, indent=2)
        
    # 2. Verify File Exists and Content
    if os.path.exists(TARGET_FILE):
        print("PASS: File created.")
        with open(TARGET_FILE, "r") as f:
            content = json.load(f)
            if content == fake_registry:
                print("PASS: Content matches.")
            else:
                print("FAIL: Content mismatch.")
    else:
        print("FAIL: File not created.")

    # 3. Simulate Alert Manager reading (Mock Logic)
    print("\nSimulating Alert Manager Read:")
    try:
        with open(TARGET_FILE, "r") as f:
            orders = json.load(f)
            print(f"Alert Manager found {len(orders)} active targets.")
            for sym, data in orders.items():
                if data.get("type") == "SPREAD":
                    print(f" - {sym}: SPREAD STOP @ SPY {data.get('stop_trigger')}")
                else:
                    print(f" - {sym}: STOP {data.get('stop')} / TAKE {data.get('take')}")
            print("PASS: Alert Manager logic simulation successful.")
    except Exception as e:
        print(f"FAIL: Alert Manager read failed: {e}")

    # Cleanup
    # os.remove(TARGET_FILE) # Keep it for manual inspection if needed

if __name__ == "__main__":
    test_sync()
