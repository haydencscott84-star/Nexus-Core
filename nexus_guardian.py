import os
import time
import datetime
import subprocess
import requests

# --- CONFIGURATION ---
CHECK_INTERVAL = 60  # seconds
SERVER_IP = "<YOUR_VPS_IP>"
from nexus_config import HEALTH_DISCORD_WEBHOOK_URL, DISCORD_WEBHOOK_URL

# Thresholds (Seconds)
MAX_AGE_SPX = 900       # 15 mins (Profiler runs every 5 mins)
MAX_AGE_BRIDGE = 300    # 5 mins (Bridge runs constantly)
MAX_AGE_SHEETS = 3600   # 1 hour (Sheets runs every 10 mins)

# File Paths (Relative to SCRIPT_DIR)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_SPX = os.path.join(SCRIPT_DIR, "nexus_spx_profile.json")
FILE_BRIDGE = os.path.join(SCRIPT_DIR, "market_state.json")
# Sheets doesn't output a file, so we check its log modification time
FILE_SHEETS_LOG = os.path.join(SCRIPT_DIR, "sheets_bridge.log")

# Service Commands
CMD_SPX = "python3 robust_wrapper.py python3 spx_profiler_nexus.py"
CMD_BRIDGE = "python3 robust_wrapper.py python3 market_bridge_v2.py"
CMD_SHEETS = "python3 robust_wrapper.py python3 nexus_sheets_bridge.py"

def send_alert(title, msg, color):
    if not HEALTH_DISCORD_WEBHOOK_URL: return
    payload = {
        "username": "🛡️ Nexus Guardian",
        "embeds": [{
            "title": title, "description": msg, "color": color,
            "footer": {"text": f"Server: {SERVER_IP} • {datetime.datetime.now().strftime('%H:%M:%S')}"}
        }]
    }
    try: requests.post(HEALTH_DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except: pass

def get_file_age(filepath):
    if not os.path.exists(filepath): return 999999
    return time.time() - os.path.getmtime(filepath)

def restart_service(name, command):
    print(f"🚨 GUARDIAN: Restarting {name}...")
    send_alert(f"🚨 GUARDIAN INTERVENTION: {name}", f"Service appeared frozen (File Age Limit Exceeded).\nRestarting...", 0xff0000)
    # Check if window exists first to avoid 'can't find window' error
    check_cmd = f"tmux list-windows -t nexus -F '#{{window_name}}' | grep -q '^{name}$'"
    is_running = (subprocess.call(check_cmd, shell=True) == 0)
    
    try:
        if is_running:
            # Window exists: Respawn it
            subprocess.run(f"tmux respawn-window -k -t nexus:{name} '{command}'", shell=True, check=True)
            send_alert(f"✅ RESTART SENT: {name}", "Respawn command executed (Window Existed).", 0x00ff00)
        else:
            # Window missing: Create new one
            # Use 'tmux new-window' but we need to assign the correct index if possible?
            # Assigning index is hard dynamically. Just create it at end (auto-index) or try to target specific if we knew it.
            # But names are unique in tmux usually.
            subprocess.run(f"tmux new-window -t nexus -n {name} '{command}'", shell=True, check=True)
            send_alert(f"✅ RESTART SENT: {name}", "New Window command executed (Window Missing).", 0x00ff00)
            
    except Exception as e:
        print(f"❌ Restart Failed: {e}")
        send_alert(f"❌ RESTART ERROR: {name}", f"Command failed: {e}", 0xff0000)

def main():
    print("🛡️ Nexus Guardian Active...")
    send_alert("🛡️ Nexus Guardian Online", "Monitoring file age heartbeats...", 0x3498db)
    
    while True:
        # 1. Check SPX Profiler
        age_spx = get_file_age(FILE_SPX)
        if age_spx > MAX_AGE_SPX:
            print(f"⚠️ SPX Profiler Frozen? (Age: {int(age_spx)}s)")
            restart_service("SPX_PROF", CMD_SPX)
            
        # 2. Check Market Bridge
        age_bridge = get_file_age(FILE_BRIDGE)
        if age_bridge > MAX_AGE_BRIDGE:
             print(f"⚠️ Market Bridge Frozen? (Age: {int(age_bridge)}s)")
             restart_service("BRIDGE", CMD_BRIDGE)
             
        # 3. Check Sheets Bridge (Log File)
        # Only check sheets during hours? No, let's keep it robust.
        # Actually Sheets Bridge V2 uses ZMQ now, maybe check log file
        age_sheets = get_file_age(FILE_SHEETS_LOG)
        # Create dummy log if not exists to prevent loop on fresh start
        if age_sheets > 900000:
             # Just touch it
             with open(FILE_SHEETS_LOG, 'a') as f: f.write("")
        elif age_sheets > MAX_AGE_SHEETS:
             print(f"⚠️ Sheets Bridge Frozen? (Log Age: {int(age_sheets)}s)")
             restart_service("SHEETS_BRIDGE", CMD_SHEETS)

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
