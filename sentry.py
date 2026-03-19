import sys
import subprocess
import requests
import time
import os

# --- CONFIG ---
DISCORD_WEBHOOK = "" # DISABLED TO STOP SPAM
# ----------------

def send_alert(script_name, error_code):
    try:
        msg = {
            "content": f"🚨 **CRASH ALERT:** `{script_name}` just died (Exit Code: {error_code}).\n\n**Action Required:** Log into VPS to investigate."
        }
        requests.post(DISCORD_WEBHOOK, json=msg)
    except:
        print("Failed to send Discord alert.")

if len(sys.argv) < 2:
    print("Usage: python3 sentry.py <script_to_run.py>")
    sys.exit(1)

target_script = sys.argv[1]
print(f"🛡️ SENTRY WATCHING: {target_script}")

# Run the target script
try:
    # This runs your script and waits for it to finish/crash
    # Pass all additional arguments to the target script
    process = subprocess.Popen([sys.executable, target_script] + sys.argv[2:])
    process.wait()
    
    if process.returncode != 0:
        print(f"\n❌ CRASH DETECTED IN {target_script}")
        send_alert(target_script, process.returncode)
        input("Press ENTER to restart this script (or Ctrl+C to exit)...")
        # Optional: Auto-restart logic could go here
    else:
        print(f"✅ {target_script} finished cleanly.")

except KeyboardInterrupt:
    print("\nSentry stopping...")
