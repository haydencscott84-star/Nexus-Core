import subprocess
import os
import signal
import sys
import datetime
import time

# List of critical scripts to monitor for duplicates
# Format: (Process Name Keyword, Max Allowed Instances)
# Note: "Max Allowed" is usually 2 (1 Wrapper + 1 Script) or 1 (if no wrapper)
TARGETS = [
    ("nexus_sweeps_tui_v2.py", 2),
    ("spx_profiler_nexus.py", 2),
    ("nexus_greeks.py", 2),
    ("gemini_market_auditor.py", 2),
    ("nexus_notifications.py", 2),
    ("nexus_debit.py", 2),
    ("ts_nexus.py", 2),
    ("watchtower_engine.py", 2),
    ("structure_nexus.py", 2),
    ("alert_manager.py", 2),
    ("nexus_hunter.py", 2),
    ("market_bridge.py", 2),
    ("analyze_snapshots.py", 2),
    ("nexus_spreads.py", 2),
    ("viewer_dash_nexus.py", 2),
    ("uw_nexus.py", 2),
    ("nexus_sweeps_tui_v1.py", 2),
    ("spy_profiler_nexus_v2.py", 2)
]

def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_processes():
    """Returns a list of dicts: {'pid': int, 'ppid': int, 'cmd': str}"""
    try:
        # ps -eo pid,ppid,args
        output = subprocess.check_output(['ps', '-eo', 'pid,ppid,args'], text=True)
        procs = []
        for line in output.splitlines()[1:]: # Skip header
            parts = line.strip().split(None, 2)
            if len(parts) < 3: continue
            try:
                procs.append({
                    'pid': int(parts[0]),
                    'ppid': int(parts[1]),
                    'cmd': parts[2]
                })
            except ValueError: pass
        return procs
    except Exception as e:
        log(f"Error fetching processes: {e}")
        return []

def run_cleanup(dry_run=False):
    log("🧟 Starting Zombie Hunter Scan...")
    procs = get_processes()
    
    # Filter for python processes
    py_procs = [p for p in procs if 'python' in p['cmd']]
    
    kill_count = 0
    
    for script_name, max_allowed in TARGETS:
        # Find all instances matches this script name
        matches = [p for p in py_procs if script_name in p['cmd']]
        
        # We need to be careful not to count the robust_wrapper as a "duplicate" of the script if the matching is too loose.
        # However, our TARGET list uses exact filenames.
        # Typically:
        # 1. python3 robust_wrapper.py python3 script.py (Matches 'script.py')
        # 2. python3 script.py (Matches 'script.py')
        # Total matches = 2.
        
        # If we see > 2, we have zombies.
        if len(matches) > max_allowed:
            log(f"⚠️  Violation: {script_name} has {len(matches)} instances (Allowed: {max_allowed})")
            
            # Action: Kill ALL of them to be safe. Wrapper will restart the good one.
            for p in matches:
                if dry_run:
                    log(f"  [DRY RUN] Would kill PID {p['pid']} ({p['cmd'][:50]}...)")
                else:
                    try:
                        os.kill(p['pid'], signal.SIGKILL)
                        log(f"  💀 Killed PID {p['pid']}")
                        kill_count += 1
                    except Exception as e:
                        log(f"  ❌ Failed to kill {p['pid']}: {e}")
    
    if kill_count > 0:
        log(f"✅ Cleanup Complete. Killed {kill_count} zombies.")
    else:
        log("✅ System Clean. No zombies found.")

if __name__ == "__main__":
    is_dry = "--dry-run" in sys.argv
    run_cleanup(dry_run=is_dry)
