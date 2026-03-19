import os
import time
import requests
import subprocess
import datetime
import socket

# --- CONFIGURATION ---
try:
    from nexus_config import HEALTH_DISCORD_WEBHOOK_URL, is_market_open
    MARKET_SCHEDULE_AVAILABLE = True
except ImportError:
    HEALTH_DISCORD_WEBHOOK_URL = ""
    MARKET_SCHEDULE_AVAILABLE = False
    def is_market_open(): return True # Fallback: Always Open

CHECK_INTERVAL = 60  # seconds
SERVER_IP = "<YOUR_VPS_IP>"

# [FIX] Updated with CORRECT script names (Win 4: greeks_engine.py, Win 1: watchtower_engine.py)
WATCH_LIST = {
    "TS_NEXUS": "python3 robust_wrapper.py python3 ts_nexus.py --headless",
    "WATCHTOWER": "python3 robust_wrapper.py python3 watchtower_engine.py --loop", # Correct: watchtower_engine.py
    "SWEEPS_V3": "python3 robust_wrapper.py python3 nexus_sweeps_v3.py",
    "GREEKS": "python3 robust_wrapper.py python3 nexus_greeks.py", # Correct: nexus_greeks.py
    "SPX_PROF": "python3 robust_wrapper.py python3 spx_profiler_nexus.py",
    "SPY_PROF": "python3 robust_wrapper.py python3 spy_profiler_nexus_v2.py",
    "STRUCTURE": "python3 robust_wrapper.py python3 structure_nexus.py",
    "ANALYZE_SNAPSHOTS": "python3 robust_wrapper.py python3 analyze_snapshots.py",
    "SHEETS_BRIDGE": "python3 robust_wrapper.py python3 nexus_sheets_bridge.py",
    "ALERTS": "python3 robust_wrapper.py python3 alert_manager.py",
    "HUNTER": "python3 robust_wrapper.py python3 nexus_hunter.py",
    "AUDITOR": "python3 robust_wrapper.py python3 gemini_market_auditor.py",
    "DASHBOARD": "python3 robust_wrapper.py python3 trader_dashboard_v3.py",
    "UW_NEXUS": "python3 robust_wrapper.py python3 uw_nexus.py",
    "VIEWER_DASH": "python3 robust_wrapper.py python3 viewer_dash_nexus.py",
    "SPREADS": "python3 robust_wrapper.py python3 nexus_spreads.py",
    "MTF_NEXUS": "./.venv/bin/python3 robust_wrapper.py ./.venv/bin/python3 mtf_nexus.py",
    "DEBIT_SNIPER": "python3 robust_wrapper.py python3 nexus_debit.py",
    "NOTIFICATIONS": "python3 robust_wrapper.py python3 nexus_notifications.py",
    "HEDGE": "python3 robust_wrapper.py python3 nexus_hedge.py",
    "OI_BOOK": "python3 robust_wrapper.py python3 nexus_oi_book.py",
    "SWEEPS_TAPE": "python3 robust_wrapper.py python3 nexus_sweeps_tui_v1.py"
}

# --- GOVERNANCE RULES ---
# RAM Limit (MB)
MEM_LIMITS = {
    "UW_NEXUS": 2500,        # Allow 2.5GB (High Volume)
    "SWEEPS_V3": 1500,       # Allow 1.5GB
    "ANALYZE_SNAPSHOTS": 1200,         # Allow 1.2GB
    "DEFAULT": 800           # Default 800MB
}

# HIBERNATE EXEMPTIONS (Services that MUST run 24/7)
HIBERNATE_EXEMPT = [
    "STRUCTURE",    # Needs pre-market calculations
    "TS_NEXUS",     # Always ready for execution
    "NOTIFICATIONS",# Always ready to alert
    "WATCHTOWER",   # Security doesn't sleep
    "SHEETS_BRIDGE" # Has its own schedule logic
]

DAILY_CLEANUP_HOUR = 4 # 4 AM Local Time
LAST_CLEANUP_DATE = None

# Scheduled Restarts (Service Name: Hour)
# tuple (Hour, Minute)
SCHEDULED_TASKS = {}
LAST_SCHEDULED_DATE = {} # {service: date_last_run}

import nexus_zombie_hunter

# --- RATE LIMITER ---
class RateLimiter:
    def __init__(self, limit=3, timeframe=3600):
        self.limit = limit
        self.timeframe = timeframe
        self.history = {} # {service_name: [timestamp1, timestamp2...]}

    def can_alert(self, service_name):
        now = time.time()
        if service_name not in self.history:
            self.history[service_name] = []
        
        # Prune old timestamps
        self.history[service_name] = [t for t in self.history[service_name] if now - t < self.timeframe]
        
        if len(self.history[service_name]) < self.limit:
            self.history[service_name].append(now)
            return True
        return False

limiter = RateLimiter(limit=15, timeframe=3600) # Increased to 15 for recovery

def send_health_alert(title, message, color):
    # Only alert if URL exists
    if not HEALTH_DISCORD_WEBHOOK_URL: return

    payload = {
        "username": "Health Center 🏥",
        "embeds": [{
            "title": title,
            "description": message,
            "color": color,
            "footer": {"text": f"Server: {SERVER_IP} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }]
    }
    try:
        requests.post(HEALTH_DISCORD_WEBHOOK_URL, json=payload, timeout=3)
    except: pass

def get_pid_by_signature(signature):
    """Returns the PID of the process matching the signature."""
    try:
        # pgrep -f matches the full command line
        output = subprocess.check_output(["pgrep", "-f", signature]).decode().strip()
        # Return the first PID found
        return output.split('\n')[0]
    except:
        return None

def get_process_stats(pid):
    """
    Returns (cpu_percent, mem_mb) for a given PID.
    Uses 'ps' command to avoid extra dependencies.
    """
    try:
        # ps -p PID -o %cpu,rss
        # rss is in KB
        output = subprocess.check_output(["ps", "-p", str(pid), "-o", "%cpu,rss", "--no-headers"]).decode().strip()
        parts = output.split()
        if len(parts) >= 2:
            cpu = float(parts[0])
            mem_mb = float(parts[1]) / 1024 # Convert KB to MB
            print(f"   Stats [PID {pid}]: CPU {cpu}% | RAM {mem_mb:.0f}MB")
            return cpu, mem_mb
    except Exception as e:
        # print(f"Stat Error: {e}")
        pass
    return 0.0, 0.0

def check_tmux_window(window_name):
    # Retrieve list of windows
    try:
        output = subprocess.check_output(["tmux", "list-windows", "-t", "nexus"], stderr=subprocess.STDOUT).decode()
        return f"{window_name}" in output
    except:
        return False

def restart_service(name, command, reason="Crash"):
    # Check Rate Limit
    if not limiter.can_alert(name):
        print(f"⚠️ RATE LIMIT: Suppressing restart/alert for {name} to prevent spam.")
        return

    print(f"🚨 RESTARTING {name} ({reason})...")
    send_health_alert(f"🚨 SERVICE RESTART: {name}", f"Reason: {reason}\nCommand: `{command}`", 0xff0000)
    
    try:
        # Check if window exists
        window_exists = check_tmux_window(name)
        
        if window_exists:
            print(f"   -> Window 'nexus:{name}' exists. Performing Hard Respawn.")
            tmux_cmd = f"tmux respawn-window -k -t nexus:{name} '{command}'"
            subprocess.run(tmux_cmd, shell=True, check=True)
        else:
            print(f"   -> Window 'nexus:{name}' MISSING. Creating new window.")
            tmux_cmd = f"tmux new-window -t nexus -n {name} '{command}'"
            subprocess.run(tmux_cmd, shell=True, check=True)
        
        time.sleep(5)
        send_health_alert(f"✅ SERVICE RESTORED: {name}", "Restart command sent. Verifying stability...", 0x00ff00)
    except Exception as e:
        send_health_alert(f"❌ RESTART FAILED: {name}", f"Error: {e}", 0x000000)

def get_script_name_from_cmd(cmd):
    parts = cmd.split()
    script_name = parts[-1] 
    for p in reversed(parts):
        if not p.startswith("-") and "." in p:
            script_name = p
            break
    if "mtf_nexus.py" in cmd: script_name = "mtf_nexus.py"
    return script_name

import zoneinfo

def get_et_now():
    tz = zoneinfo.ZoneInfo("America/New_York")
    return datetime.datetime.now(tz).replace(tzinfo=None)

def main_loop():
    print("🏥 Watchdog v2 (The Sheriff) Active...")
    print(f"   Config: Market Schedule={'ENABLED' if MARKET_SCHEDULE_AVAILABLE else 'DISABLED'}")
    send_health_alert("Hiber-Nation Active", "Watchdog v2 Online. Monitoring Resources & Schedule.", 0x3498db)
    
    while True:
        # 1. Check Hibernate Mode
        market_open = is_market_open()
        
        # 2. Iterate over all monitored services
        for name, cmd in WATCH_LIST.items():
            
            # --- HIBERNATE CHECK ---
            if not market_open and name not in HIBERNATE_EXEMPT:
                # In off-hours, we do NOT restart non-exempt services.
                # We could purposefully KILL them here to save resources,
                # but for Phase 1, we just stop reviving them. 
                # (Self-management scripts like sweep_v3 will sleep themselves)
                continue
                
            script_name = get_script_name_from_cmd(cmd)
            
            # 3. Check Vital Signs
            pid = get_pid_by_signature(script_name)
            
            if not pid:
                # Dead? Wait 1s and check again
                time.sleep(1)
                if not get_pid_by_signature(script_name):
                    restart_service(name, cmd, reason="Process Missing")
            else:
                # Alive -> Check Compliance
                cpu, mem = get_process_stats(pid)
                
                # A. Memory Cap
                limit = MEM_LIMITS.get(name, MEM_LIMITS["DEFAULT"])
                if mem > limit:
                    restart_service(name, cmd, reason=f"OOM KILL: {mem:.0f}MB > {limit}MB")
                    time.sleep(5) # Give it time to die
                    
                # B. CPU Cap (Simple check for now)
                # If CPU > 95%? Maybe too aggressive for single check. 
                # TODO: Implement persistence check for CPU.
                if cpu > 95.0:
                    print(f"⚠️ HIGH CPU: {name} at {cpu}%")

        # 3. Daily Zombie Cleanup
        global LAST_CLEANUP_DATE
        now = datetime.datetime.now()
        if now.hour == DAILY_CLEANUP_HOUR and now.date() != LAST_CLEANUP_DATE:
            print(f"🧹 Performing Daily Zombie Cleanup ({now})...")
            try:
                nexus_zombie_hunter.run_cleanup()
                LAST_CLEANUP_DATE = now.date()
                send_health_alert("🧹 Daily System Cleanup", "Zombie Hunter executed.", 0xe67e22)
            except Exception as e:
                send_health_alert("❌ Cleanup Failed", f"Error: {e}", 0xff0000)
            
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main_loop()
