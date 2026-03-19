import json
import time
import os

TARGET_FILE = "active_targets.json"

print(f"[*] Testing Target Sync File: {os.path.abspath(TARGET_FILE)}")

# 1. Simulate Dashboard Writing
print("[*] Simulating Dashboard Write...")
targets = {
    "SPY": {"stop": 694.20, "take": 670.00, "type": "PUT"},
    "NVDA": {"stop": 120.00, "take": 150.00, "type": "CALL"}
}

try:
    with open(TARGET_FILE, "w") as f:
        json.dump(targets, f, indent=4)
    print("[+] Successfully wrote to active_targets.json")
except Exception as e:
    print(f"[-] Failed to write: {e}")

# 2. Verify Content
print("[*] Verifying Content...")
try:
    with open(TARGET_FILE, "r") as f:
        data = json.load(f)
    print(f"[+] Read Data: {data}")
except Exception as e:
    print(f"[-] Failed to read: {e}")

print("\n[*] Now run 'python3 alert_manager.py' in another tab.")
print("[*] It should print: [GUARDIAN] New Targets Received: ['SPY', 'NVDA']")
print("[*] Waiting 10 seconds then clearing targets...")
time.sleep(10)

# 3. Clear Targets
print("[*] Clearing Targets...")
with open(TARGET_FILE, "w") as f:
    json.dump({}, f)
print("[+] Targets Cleared.")
