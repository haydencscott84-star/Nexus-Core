import subprocess
import sys
import os
import datetime

# EXPECTED SERVICES MAP 
# (Window Name, Expected Script Substring)
SERVICES = [
    ("TS_NEXUS", "ts_nexus.py"),
    ("WATCHTOWER", "watchtower_engine.py"),
    ("NOTIFICATIONS", "nexus_notifications.py"),
    ("BRIDGE", "market_bridge_v2.py"),
    ("SPX_PROF", "spx_profiler_nexus.py"),
    ("SPY_PROF", "spy_profiler_nexus_v2.py"),
    ("STRUCTURE", "structure_nexus.py"),
    ("ANALYZE_SNAPSHOTS", "analyze_snapshots.py"),
    ("ALERTS", "alert_manager.py"),
    ("GUARDIAN", "nexus_guardian.py"),
    ("HUNTER", "nexus_hunter.py"),
    ("AUDITOR", "gemini_market_auditor.py"),
    ("UW_NEXUS", "uw_nexus.py"),
    ("TRADER_DASH", "trader_dashboard_v3.py"),
    ("VIEWER_DASH", "viewer_dash_nexus.py"),
    ("SPREADS", "nexus_spreads.py"),
    ("DEBIT_SNIPER", "nexus_debit.py"),
    ("MTF_NEXUS", "mtf_nexus.py"),
    ("SWEEPS_V3", "nexus_sweeps_v3.py"),
    ("GREEKS", "nexus_greeks.py"),
    ("HEDGE", "nexus_hedge.py"),
    ("WATCHDOG", "system_watchdog.py"),
    ("SHEETS_BRIDGE", "nexus_sheets_bridge.py"),
    ("GEX_WORKER", "gex_worker_nexus.py")
]

def run(cmd):
    try:
        return subprocess.check_output(cmd, shell=True).decode().strip()
    except:
        return ""

def check_health():
    print(f"\n🩺 SYSTEM HEALTH CHECK - {datetime.datetime.now()}")
    print("="*60)
    print(f"{'SERVICE (WIN)':<20} | {'WINDOW':<8} | {'PROCESS':<8} | {'STATUS'}")
    print("-" * 60)

    # 1. Get Tmux Windows
    tmux_out = run("tmux list-windows -t nexus -F '#I:#W'")
    active_windows = {} # ID -> Name
    active_names = []
    if tmux_out:
        for line in tmux_out.split('\n'):
            if ':' in line:
                i, name = line.split(':', 1)
                active_windows[name.upper().strip()] = i
                active_names.append(name.upper().strip())

    # 2. Get Running Python Processes
    ps_out = run("pgrep -af python")
    
    overall_status = True

    for svc_name, script_frag in SERVICES:
        # Match Window
        win_id = "N/A"
        win_ok = False
        
        # Fuzzy match window name
        found_key = None
        for k in active_windows:
            if svc_name in k or k in svc_name:
                win_id = active_windows[k]
                win_ok = True
                found_key = k
                break
        
        # Match Process
        proc_ok = False
        if script_frag in ps_out:
            proc_ok = True
        
        status = "✅ UP"
        if not win_ok and not proc_ok:
            status = "🔴 DOWN (Dead)"
            overall_status = False
        elif not win_ok:
            status = "⚠️  Zombie (No Window)"
            overall_status = False
        elif not proc_ok:
            status = "⚠️  Frozen (No Proc)"
            overall_status = False
            
    # 3. Check Log Freshness (Stuck Process Detection)
    # Map Service -> Log File to check
    LOG_CHECKS = {
        "BRIDGE": "bridge_persistence.json", # Changed to persistence file as it's critical
        "TS_NEXUS": "nexus_engine.log",
        "SWEEPS_V3": "nexus_sweeps_v3.json",  
        "SPX_PROF": "nexus_spx_profile.json",
        "AUDITOR": "market_state.json"
    }

    now = datetime.datetime.now().timestamp()

    for svc_name, script_frag in SERVICES:
        # Match Window
        win_id = "N/A"
        win_ok = False
        
        # Fuzzy match window name
        for k in active_windows:
            if svc_name in k or k in svc_name:
                win_id = active_windows[k]
                win_ok = True
                break
        
        # Match Process
        proc_ok = False
        if script_frag in ps_out:
            proc_ok = True
        
        status = "✅ UP"
        if not win_ok and not proc_ok:
            status = "🔴 DOWN (Dead)"
            overall_status = False
        elif not win_ok:
            status = "⚠️  Zombie (No Window)"
            overall_status = False
        elif not proc_ok:
            status = "⚠️  Frozen (No Proc)"
            overall_status = False
        
        # Freshness Check
        fresh_info = ""
        if proc_ok and svc_name in LOG_CHECKS:
            log_f = LOG_CHECKS[svc_name]
            if os.path.exists(log_f):
                mtime = os.path.getmtime(log_f)
                age = now - mtime
                if age > 120: # 2 minutes
                    status = "⚠️  STUCK (Stale Log)"
                    fresh_info = f"[Lag: {int(age)}s]"
                    overall_status = False
                else:
                    fresh_info = f"[OK: {int(age)}s]"
            
        print(f"{svc_name:<20} | {str(win_id):<8} | {'YES' if proc_ok else 'NO':<8} | {status} {fresh_info}")

    print("="*60)
    if overall_status:
        print("✅ SYSTEM STABLE")
    else:
        print("⚠️  SYSTEM UNSTABLE - INTERVENTION REQUIRED")

if __name__ == "__main__":
    check_health()
