import sys
import subprocess
import time
import requests
import datetime
import random
import signal
import os

# --- HARDENED ARCHITECTURE V2 ---
# Implements SIGNAL PROPAGATION to prevent Zombie Processes.
# When this wrapper gets killed (SIGTERM/SIGINT), it kills the child first.

def send_alert(title, msg, color=16711680):
    # (Optional Discord Alert - Disabled to prevent spam loop during crashes)
    pass

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 robust_wrapper.py <command> [args...]")
        sys.exit(1)

    cmd = sys.argv[1:]
    cmd_str = " ".join(cmd)
    
    print(f"🛡️ ROBUST WRAPPER V2: Protecting '{cmd_str}'")
    
    crash_count = 0
    current_process = None

    # --- SIGNAL HANDLING ---
    def shutdown_handler(signum, frame):
        print(f"\n🛑 WRAPPER RECEIVED SIGNAL {signum}. Terminating child...")
        if current_process:
            try:
                # Forward the signal to the child
                current_process.send_signal(signum)
                # Wait for child to exit to avoid zombies
                current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("💀 Child refused to die. Force killing (SIGKILL)...")
                current_process.kill()
            except Exception as e:
                pass
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    while True:
        print(f"\n🚀 Launching: {cmd_str}")
        start_time = time.time()
        
        try:
            # [HARDENING] Pre-Launch Zombie Cleanup
            # If we are restarting, ensure no previous instance logic is hanging.
            # While nexus_lock handles singletons, it returns exit(1) if locked.
            # If we see immediate exit(1), we might have a zombie capable of being killed.
            
            # Run the command
            current_process = subprocess.Popen(cmd)
            current_process.wait() # Blocks here until child exits OR signal received
            exit_code = current_process.returncode
            
            # [HARDENING] If Exit Code 1 (Lock Error) AND Run Duration < 2s
            # It implies a Zombie is holding the lock.
            if exit_code == 1 and (time.time() - start_time) < 2.0:
                 print("💀 LOCK CONTENTION DETECTED. Attempting to kill zombies...")
                 target_script = cmd[-1] # e.g. gemini_market_auditor.py
                 if ".py" in target_script:
                      os.system(f"pkill -f {target_script}")
                      time.sleep(1) # Allow release
        
        except Exception as e:
            print(f"❌ Launch failed: {e}")
            exit_code = 1
        finally:
            current_process = None

        # Check duration to reset crash count
        run_duration = time.time() - start_time
        if run_duration > 60:
            crash_count = 0

        # CRASH LOGIC
        if exit_code != 0 and exit_code != -15 and exit_code != -2: # Ignore SIGTERM(-15)/SIGINT(-2) exits
            crash_count += 1
            print(f"⚠️ CRASH DETECTED (Code {exit_code}). Crash Count: {crash_count}")
            
            if crash_count > 5:
                print("⛔ TOO MANY CRASHES. Pausing for 60s...")
                time.sleep(60)
                crash_count = 0
            else:
                jitter = random.randint(2, 6)
                print(f"⏳ Waiting {jitter}s before restart...")
                time.sleep(jitter)
        else:
            print(f"✅ Process exited (Code {exit_code}). Restarting in 2s...")
            time.sleep(2)

if __name__ == "__main__":
    main()
