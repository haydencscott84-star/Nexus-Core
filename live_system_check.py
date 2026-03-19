import os
import json
import sys

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REQUIRED_FILES = [
    "spy_thesis.json",
    "nexus_structure.json",
    "nexus_portfolio.json"
]

def check_system():
    print("🔍 RUNNING FINAL SYSTEM CHECK...")
    print("-" * 40)
    
    all_good = True
    
    for filename in REQUIRED_FILES:
        filepath = os.path.join(SCRIPT_DIR, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    # Basic validation
                    if not data:
                        print(f"⚠️  {filename} exists but is EMPTY.")
                        all_good = False
                    else:
                        print(f"✅ {filename} FOUND and READABLE.")
            except Exception as e:
                print(f"❌ {filename} exists but is CORRUPT: {e}")
                all_good = False
        else:
            print(f"❌ {filename} MISSING.")
            all_good = False
            
    print("-" * 40)
    if all_good:
        print("✅ SYSTEM READY FOR LIVE TRADING")
    else:
        print("❌ SYSTEM NOT READY. Fix missing or corrupt files.")

if __name__ == "__main__":
    check_system()
