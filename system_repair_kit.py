import os
import time
import subprocess
import json
import sys

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def log(msg):
    print(f"🔧 [REPAIR] {msg}")

def write_dummy_portfolio():
    filepath = os.path.join(SCRIPT_DIR, "nexus_portfolio.json")
    if not os.path.exists(filepath):
        log("Seeding nexus_portfolio.json...")
        data = {
            "active_trade": {
                "ticker": "SPY",
                "qty": 10,
                "type": "PUT",
                "strike": 590.0,
                "expiry": "2025-12-19",
                "direction": "BEAR"
            }
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    else:
        log("nexus_portfolio.json exists. Skipping seed.")

def run_process(cmd, bg=False):
    log(f"Running: {cmd}")
    if bg:
        return subprocess.Popen(cmd, shell=True, cwd=SCRIPT_DIR)
    else:
        subprocess.run(cmd, shell=True, cwd=SCRIPT_DIR)

def main():
    log("Starting System Repair & Verification...")
    
    # 1. Seed Portfolio (Required for Greeks)
    write_dummy_portfolio()
    
    # 2. Launch Producers
    procs = []
    
    # Watchtower (Background - needs to run loop or just once? It runs once by default unless --loop)
    # Let's run it once to generate file.
    run_process("python3 watchtower_engine.py")
    
    # Sweeps (Headless - Once)
    run_process("python3 nexus_sweeps_tui_v2.py --headless")
    
    # TS Nexus (Simulation - Background Loop)
    p_ts = run_process("python3 ts_nexus.py --simulation", bg=True)
    procs.append(p_ts)
    
    # Greeks (Background Loop - needs to run for a bit)
    p_greeks = run_process("python3 nexus_greeks.py", bg=True)
    procs.append(p_greeks)
    
    # Structure (Run Once - it has a main loop but we can just import/run or assume it's fresh enough or run it in bg)
    # Let's run it in BG
    p_struct = run_process("python3 structure_nexus.py", bg=True)
    procs.append(p_struct)
    
    log("Waiting 15s for data to populate...")
    time.sleep(15)
    
    # 3. Verify
    log("Running Verification...")
    run_process("python3 verify_data_flow.py")
    
    # 4. Cleanup
    log("Cleaning up background processes...")
    for p in procs:
        p.terminate()
        
    # Force Kill to be sure
    run_process("pkill -f 'ts_nexus.py --simulation'")
    run_process("pkill -f 'nexus_greeks.py'")
    run_process("pkill -f 'structure_nexus.py'")
    
    log("Repair Complete.")

if __name__ == "__main__":
    main()
