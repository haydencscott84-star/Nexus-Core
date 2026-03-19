import json
import os
import time
import datetime
import sys

# --- CONFIG ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAX_AGE_SECONDS = 300 # 5 Minutes (Warning threshold)

# FILES TO AUDIT
# Format: "Filename": "Producer Script"
FILES = {
    "market_state_live.json": "watchtower_engine.py",
    "market_state.json": "market_bridge.py",
    "nexus_tape.json": "ts_nexus.py",
    "nexus_structure.json": "structure_nexus.py",
    "nexus_sweeps_v2.json": "nexus_sweeps_tui_v2.py",
    "nexus_greeks.json": "nexus_greeks.py",
    "market_health.json": "market_health_monitor.py"
}

def check_file(filename, producer):
    filepath = os.path.join(SCRIPT_DIR, filename)
    
    if not os.path.exists(filepath):
        return f"❌ MISSING: {filename} (Producer: {producer})"
    
    try:
        # Check Metadata Age
        mtime = os.path.getmtime(filepath)
        age = time.time() - mtime
        age_str = f"{age:.0f}s ago"
        
        # Read Content
        with open(filepath, "r") as f:
            data = json.load(f)
            
        # Check Internal Timestamp (if exists)
        internal_ts = data.get("timestamp")
        internal_age_str = "N/A"
        if internal_ts:
            # Handle ISO format or float
            try:
                if isinstance(internal_ts, str):
                    dt = datetime.datetime.fromisoformat(internal_ts)
                    ts_val = dt.timestamp()
                else:
                    ts_val = float(internal_ts)
                
                internal_age = time.time() - ts_val
                internal_age_str = f"{internal_age:.0f}s latency"
            except: pass

        # Status Logic
        status_icon = "✅"
        if age > MAX_AGE_SECONDS:
            status_icon = "⚠️ STALE"
        
        # Content Summary
        keys = list(data.keys())[:3]
        content_preview = f"Keys: {keys}..."
        
        return f"{status_icon} {filename:<25} | Age: {age_str:<10} | Internal: {internal_age_str:<12} | {content_preview}"

    except Exception as e:
        return f"❌ ERROR: {filename} - {e}"

def main():
    print("\n🔍 === DATA FLOW AUDIT === 🔍")
    print(f"Time: {datetime.datetime.now().strftime('%H:%M:%S')}\n")
    
    for filename, producer in FILES.items():
        report = check_file(filename, producer)
        print(report)
        
    print("\n===========================")

if __name__ == "__main__":
    main()
