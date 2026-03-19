import subprocess
import os
import time
import sys
import datetime
import requests
import signal
from collections import deque

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(SCRIPT_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Discord Webhook (From sentry.py)
DISCORD_WEBHOOK = "" # DISABLED TO STOP SPAM

# SUBSYSTEMS TO MANAGE
# Format: "Script Name": "Log Filename"
# CORE SUBSYSTEMS (Backend - Safe to Supervise)
CORE_SUBSYSTEMS = {
    # --- 1. DATA LAYER (Producers) ---
    "watchtower_engine.py --loop": "watchtower.log",  # Risk Regime (Light)
    "ts_nexus.py": "tape.log",                        # Price Feed (Heavy)
    "nexus_greeks.py": "greeks.log",                  # Greeks (Medium)
    "spx_profiler_nexus.py": "spx.log",               # SPX Profile (Medium)
    "spy_profiler_nexus_v2.py": "spy_prof.log",       # SPY Profile (Medium) [Added from cockpit]
    "uw_nexus.py": "uw_nexus.log",                    # UW Data [Added from cockpit]
    
    # --- 2. LOGIC LAYER (Consumers) ---
    "structure_nexus.py": "structure.log",            # Market Structure
    "analyze_snapshots.py --headless": "history.log", # Historical Analysis
    "market_bridge.py": "bridge.log",                 # Order Bridge
    
    # --- 3. BRAIN LAYER (Decision) ---
    "alert_manager.py": "alerts.log",                 # Alert Manager
    "nexus_hunter.py": "hunter.log",                  # The Hunter
    "gemini_market_auditor.py": "auditor.log",        # The Auditor
}

# UI SUBSYSTEMS (Frontend - Optional for Headless)
UI_SUBSYSTEMS = {
    "nexus_sweeps_tui_v2.py --headless": "sweeps_v2.log", # Sweeps (Heavy)
    "nexus_sweeps_tui_v1.py --headless": "sweeps_v1.log", # Sweeps V1 (Classic)
    # "viewer_dash_nexus.py": "dash.log",                   # Dashboard Viewer (MUST RUN MANUALLY)
    "news_client.py --headless": "news.log",              # News Feed (Headless)
    "nexus_spreads.py": "spreads.log"                     # Spreads TUI
}

# Default: Run EVERYTHING
SUBSYSTEMS = {**CORE_SUBSYSTEMS, **UI_SUBSYSTEMS}

# Crash Loop Protection: Max 3 restarts in 60 seconds
MAX_RESTARTS = 3
CRASH_WINDOW = 60 

class NexusSupervisor:
    def __init__(self):
        self.processes = {} # script_name -> Popen object
        self.crash_history = {} # script_name -> deque([timestamps])
        self.running = True
        
        # Handle Ctrl+C
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def send_alert(self, title, msg, color=16711680): # Red default
        if not DISCORD_WEBHOOK: return
        try:
            payload = {
                "embeds": [{
                    "title": title,
                    "description": msg,
                    "color": color,
                    "timestamp": datetime.datetime.now().isoformat()
                }]
            }
            requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
        except: pass

    def launch_process(self, script_cmd, log_file):
        """Launches a process and stores the Popen object."""
        log_path = os.path.join(LOG_DIR, log_file)
        
        # Split command for Popen (e.g. "script.py --arg" -> ["script.py", "--arg"])
        parts = script_cmd.split(" ")
        script_name = parts[0]
        args = parts[1:]
        
        full_cmd = [sys.executable, "-u", script_name] + args
        
        try:
            # Open log file
            with open(log_path, "a") as f:
                f.write(f"\n\n--- LAUNCHING AT {datetime.datetime.now()} ---\n")
                
            # Launch
            # We redirect stdout/stderr to the log file
            # We use start_new_session=True to ensure signals don't propagate weirdly if we don't want them to
            f = open(log_path, "a")
            p = subprocess.Popen(full_cmd, stdout=f, stderr=f, cwd=SCRIPT_DIR)
            
            self.processes[script_cmd] = p
            print(f"🚀 Started: {script_cmd} (PID: {p.pid})")
            return True
        except Exception as e:
            print(f"❌ Failed to launch {script_cmd}: {e}")
            return False

    def check_crash_loop(self, script_cmd):
        """Returns True if safe to restart, False if in crash loop."""
        now = time.time()
        if script_cmd not in self.crash_history:
            self.crash_history[script_cmd] = deque(maxlen=MAX_RESTARTS)
        
        history = self.crash_history[script_cmd]
        
        # Remove old timestamps
        while history and now - history[0] > CRASH_WINDOW:
            history.popleft()
            
        if len(history) >= MAX_RESTARTS:
            return False
            
        history.append(now)
        return True

    def monitor_loop(self):
        print("🛡️ NEXUS SUPERVISOR ACTIVE. Monitoring subsystems...")
        self.send_alert("Nexus Supervisor Started", "System is coming online.", 3447003) # Blue
        
        # Initial Launch
        for script, log in SUBSYSTEMS.items():
            self.launch_process(script, log)
            
        while self.running:
            for script, log in SUBSYSTEMS.items():
                p = self.processes.get(script)
                
                # Check if process is dead
                if p and p.poll() is not None:
                    exit_code = p.returncode
                    print(f"⚠️ CRASH DETECTED: {script} (Exit: {exit_code})")
                    
                    # Crash Loop Check
                    if exit_code == 0:
                        print(f"ℹ️ {script} exited cleanly (Code 0). Restarting...")
                        # Do NOT alert on clean exit, just restart
                        self.launch_process(script, log)
                    elif self.check_crash_loop(script):
                        print(f"🔄 Restarting {script}...")
                        self.send_alert("Service Restarted", f"`{script}` crashed (Code {exit_code}). Restarting...", 16776960) # Yellow
                        self.launch_process(script, log)
                    else:
                        print(f"⛔ CRASH LOOP: {script}. Giving up.")
                        self.send_alert("CRITICAL FAILURE", f"`{script}` is in a crash loop. **Manual intervention required.**", 16711680) # Red
                        del self.processes[script] # Stop monitoring this one
                
                # Check if process was never started (e.g. failed initial launch)
                elif not p:
                     # Attempt to start if not in crash loop (using same logic)
                     if self.check_crash_loop(script):
                         self.launch_process(script, log)

            time.sleep(5)

    def shutdown(self, signum, frame):
        print("\n🛑 SHUTDOWN SIGNAL RECEIVED. Terminating subsystems...")
        self.running = False
        for script, p in self.processes.items():
            if p.poll() is None:
                print(f"   🔪 Killing {script}...")
                p.terminate()
                try:
                    p.wait(timeout=2)
                except:
                    p.kill()
        print("✅ All systems offline.")
        sys.exit(0)

def kill_zombies():
    print("🧹 Cleaning up old processes...")
    subprocess.run(["pkill", "-f", "python3.*nexus_"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "python3.*market_"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "python3.*watchtower"], stderr=subprocess.DEVNULL)
    subprocess.run(["pkill", "-f", "options_obv_tui.py"], stderr=subprocess.DEVNULL) # Ensure old TUI is dead
    # Add more specific patterns if needed, but be careful not to kill the supervisor itself if it matches!
    # The supervisor is running as "nexus_launcher.py", so we should avoid killing that if we are restarting.
    # But if this is a fresh start, we might want to kill old supervisors.
    
if __name__ == "__main__":
    if "--reset" in sys.argv:
        kill_zombies()
        
    supervisor = NexusSupervisor()
    supervisor.monitor_loop()
