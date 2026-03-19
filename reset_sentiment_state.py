import os
import datetime

files = ["spx_sentiment_state.json", "spy_sentiment_state.json"]

print("[-] Removing Poisoned State Files...")
for f in files:
    if os.path.exists(f):
        try:
            os.remove(f)
            print(f"    [x] Deleted {f}")
        except Exception as e:
            print(f"    [!] Failed to delete {f}: {e}")
    else:
        print(f"    [ ] {f} not found.")

print("[+] State Reset Complete. Restart Profilers to Replay History.")
