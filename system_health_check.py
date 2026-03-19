import zmq
import os
import json
import time
import sys
import datetime

# --- CONFIG ---
PORTS = {
    "MARKET": 5555,
    "ACCOUNT": 5566,
    "EXEC": 5567,
    "CONTROL": 5568,
    "LOGS": 5572
}

FILES = [
    "market_state.json",
    "nexus_tape.json",
    "nexus_structure.json"
]

def check_port(name, port):
    try:
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.connect(f"tcp://127.0.0.1:{port}")
        # Just checking if we can connect without error is a basic check.
        # A real check would need a ping/pong protocol, but we'll assume open if no immediate error.
        sock.close()
        ctx.term()
        return True
    except:
        return False

def check_file(filename):
    if not os.path.exists(filename):
        return "MISSING", 0
    
    try:
        mtime = os.path.getmtime(filename)
        age = time.time() - mtime
        with open(filename, 'r') as f:
            json.load(f)
        return "OK", age
    except:
        return "CORRUPT", 0

def main():
    print("🏥 SYSTEM HEALTH CHECK")
    print(f"Time: {datetime.datetime.now()}")
    print("-" * 30)
    
    all_good = True
    
    print("🔌 ZMQ PORTS:")
    for name, port in PORTS.items():
        # Using lsof to check if ANY process is listening
        res = os.system(f"lsof -i:{port} > /dev/null 2>&1")
        status = "OPEN" if res == 0 else "CLOSED"
        color = "✅" if status == "OPEN" else "❌"
        print(f"   {color} {name} ({port}): {status}")
        if status == "CLOSED": all_good = False

    print("\n📄 DATA FILES:")
    for f in FILES:
        status, age = check_file(f)
        color = "✅" if status == "OK" and age < 60 else "❌"
        age_str = f"{age:.1f}s ago" if status == "OK" else "-"
        print(f"   {color} {f}: {status} ({age_str})")
        if status != "OK" or age > 60: all_good = False

    print("-" * 30)
    if all_good:
        print("✅ SYSTEM HEALTHY")
        sys.exit(0)
    else:
        print("⚠️ ISSUES DETECTED")
        sys.exit(1)

if __name__ == "__main__":
    main()
