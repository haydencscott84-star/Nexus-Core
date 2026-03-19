import sys
import os
import asyncio
from unittest.mock import MagicMock

# Mock ZMQ to prevent actual connections during test
sys.modules["zmq"] = MagicMock()
sys.modules["zmq.asyncio"] = MagicMock()

print("🔵 STARTING STABILITY CHECK...")

try:
    print("1. Importing ts_nexus...")
    import ts_nexus
    print("   ✅ ts_nexus imported successfully.")
    
    print("2. Importing trader_dashboard...")
    import trader_dashboard
    print("   ✅ trader_dashboard imported successfully.")

    print("3. Checking NexusEngine Class...")
    # We can't easily instantiate because of ZMQ usage in __init__, 
    # but successful import proves syntax and class definition are valid.
    # Let's try to inspect the class to ensure it's well-formed.
    if hasattr(ts_nexus, 'NexusEngine'):
        print("   ✅ NexusEngine class found.")
    else:
        print("   ❌ NexusEngine class NOT found.")
        sys.exit(1)

    print("4. Checking TraderDashboardV2 Class...")
    if hasattr(trader_dashboard, 'TraderDashboardV2'):
        print("   ✅ TraderDashboardV2 class found.")
    else:
        print("   ❌ TraderDashboardV2 class NOT found.")
        sys.exit(1)

    print("\n🟢 STABILITY CHECK PASSED: All modules loaded without errors.")

except Exception as e:
    print(f"\n🔴 CRITICAL FAILURE: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
