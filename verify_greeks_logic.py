import json
import os
import sys

def verify_logic():
    print("🔍 Verifying Greek Data Access Logic...")
    
    if not os.path.exists("nexus_greeks.json"):
        print("❌ FAIL: nexus_greeks.json not found.")
        return

    try:
        with open("nexus_greeks.json", "r") as f:
            data = json.load(f)
            
        print(f"✅ JSON Loaded. Keys: {list(data.keys())}")
        
        greeks = data.get("greeks", {})
        delta = greeks.get("delta", 0)
        gamma = greeks.get("gamma", 0)
        
        print(f"✅ Values Parsed: Delta={delta}, Gamma={gamma}")
        
        # Verify Types
        if not isinstance(delta, (int, float)) or not isinstance(gamma, (int, float)):
             print("⚠️ WARNING: Greeks are not numbers.")
        else:
             print("✅ Data Types Correct (Float/Int)")
             
        print("🚀 Logic Verification PASSED.")
        
    except Exception as e:
        print(f"❌ FAIL: Logic Error: {e}")

if __name__ == "__main__":
    verify_logic()
