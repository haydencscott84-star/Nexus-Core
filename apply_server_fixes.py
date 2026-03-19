import os
import sys
import json
import time
import subprocess

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def patch_auditor():
    log("Patching gemini_market_auditor.py...")
    try:
        with open("gemini_market_auditor.py", "r") as f:
            content = f.read()
        
        # Unconditional 1 hour sleep for off-hours
        new_content = content.replace("sleep_seconds = 14400", "sleep_seconds = 3600")
        
        # Also ensure it logs appropriately
        if "sleep_seconds = 3600" in new_content:
            log("✅ patched sleep duration")
        else:
            log("⚠️ could not match sleep duration string")
            
        with open("gemini_market_auditor.py", "w") as f:
            f.write(new_content)
            
    except Exception as e:
        log(f"❌ Failed to patch auditor: {e}")

def patch_snapshots():
    log("Patching analyze_snapshots.py...")
    try:
        with open("analyze_snapshots.py", "r") as f:
            lines = f.readlines()
        
        new_lines = []
        patched = False
        
        for line in lines:
            # Look for the normalization line at end of load_unified_data
            if "master['norm_strike'] =" in line and "apply" in line:
                new_lines.append(line)
                
                # INSERT FILTER LOGIC
                indent = line[:len(line)-len(line.lstrip())]
                new_lines.append(f"{indent}# --- FILTER USELESS STRIKES ---\n")
                new_lines.append(f"{indent}try:\n")
                new_lines.append(f"{indent}    if 'underlying_price' in master.columns:\n")
                new_lines.append(f"{indent}        valid_prices = master[master['underlying_price'] > 0]['underlying_price']\n")
                new_lines.append(f"{indent}        if not valid_prices.empty:\n")
                new_lines.append(f"{indent}            spot = valid_prices.iloc[-1]\n")
                new_lines.append(f"{indent}            # Keep strikes within 20% of spot (e.g. 544-816 for 680)\n")
                new_lines.append(f"{indent}            # Use norm_strike to handle SPX/SPY mix\n")
                new_lines.append(f"{indent}            master = master[(master['norm_strike'] >= spot * 0.8) & (master['norm_strike'] <= spot * 1.2)]\n")
                new_lines.append(f"{indent}            print(f'✅ Filtered to {{len(master)}} rows near spot {{spot}}')\n")
                new_lines.append(f"{indent}except Exception as e: print(f'Filter Error: {{e}}')\n")
                
                patched = True
                continue
            
            new_lines.append(line)
            
        if patched:
            with open("analyze_snapshots.py", "w") as f:
                f.writelines(new_lines)
            log("✅ patched analyze_snapshots strike filter")
        else:
            log("⚠️ could not find insertion point in analyze_snapshots")

    except Exception as e:
        log(f"❌ Failed to patch snapshots: {e}")

def reset_targets():
    log("Resetting active_targets.json...")
    try:
        with open("active_targets.json", "w") as f:
            f.write("{}")
        log("✅ active_targets.json cleared")
    except Exception as e:
        log(f"❌ Failed to reset targets: {e}")

def restart_services():
    log("Restarting Services...")
    services = ["gemini_market_auditor.py", "analyze_snapshots.py", "ts_nexus.py"]
    
    for s in services:
        os.system(f"pkill -f {s}")
        time.sleep(1)
        # Restart
        cmd = f"nohup python3 {s} >/dev/null 2>&1 &"
        os.system(cmd)
        log(f"🚀 Restarted {s}")

if __name__ == "__main__":
    patch_auditor()
    patch_snapshots()
    reset_targets()
    restart_services()
