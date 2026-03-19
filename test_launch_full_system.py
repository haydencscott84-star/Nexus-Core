import sys
import os
import asyncio
import time
import json
import threading
from datetime import datetime

import subprocess

# Mock Args
class MockArgs:
    headless = True
    debug = True

def test_cli_launch(script_name):
    print(f"\n🧪 Testing CLI Launch: {script_name} --headless...")
    try:
        # Run for 3 seconds then kill
        proc = subprocess.Popen(
            ["python3", script_name, "--headless"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(3)
        
        if proc.poll() is not None:
            # It exited early -> CRASH
            stdout, stderr = proc.communicate()
            print(f"   ❌ {script_name} CRASHED immediately!")
            print(f"   STDERR:\n{stderr}")
            return False
        else:
            # Still running -> SUCCESS
            proc.terminate()
            print(f"   ✅ {script_name} launched successfully (ran for 3s).")
            return True
            
    except Exception as e:
        print(f"   ❌ CLI Test Failed: {e}")
        return False

def test_v1_launch():
    print("\n🧪 Testing V1 Launch (nexus_sweeps_tui_v1.py)...")
    try:
        from nexus_sweeps_tui_v1 import NexusSweeps
        app = NexusSweeps()
        app.HEADLESS = True
        
        # We can't easily run app.run() because it blocks.
        # But we can test the on_mount logic by calling it manually?
        # Textual apps are hard to test without running the loop.
        # We will try to run it in a separate thread/process or just verify instantiation and method existence.
        
        print("   ✅ Instantiation successful.")
        
        # Verify fetch_backfill_logic exists and is a coroutine
        if not asyncio.iscoroutinefunction(app.fetch_backfill_logic):
            print("   ❌ fetch_backfill_logic is NOT a coroutine!")
            return False
        print("   ✅ fetch_backfill_logic structure OK.")
        
        return True
    except Exception as e:
        print(f"   ❌ V1 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_v2_launch():
    print("\n🧪 Testing V2 Launch (nexus_sweeps_tui_v2.py)...")
    try:
        from nexus_sweeps_tui_v2 import NexusSwingEvents
        app = NexusSwingEvents()
        app.HEADLESS = True
        print("   ✅ Instantiation successful.")
        return True
    except Exception as e:
        print(f"   ❌ V2 CRASHED: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_copycat_logic():
    print("\n🧪 Testing Copycat Optimizer (Theo/Edge)...")
    try:
        from nexus_copycat_bot import CopycatOptimizer
        opt = CopycatOptimizer()
        
        # Mock Whale Signal
        whale_sig = {
            "type": "WHALE_ALERT",
            "expiration": "2026-06-20",
            "option_type": "C",
            "zone_strike": 550,
            "notional": 5_000_000,
            "volume": 2000,
            "dte": 200,
            "strikes": [550, 555]
        }
        
        res = opt.optimize(whale_sig)
        print(f"   -> Result: {res}")
        
        if "retail_contract" in res and "edge" in res:
            print("   ✅ Optimizer returned valid structure.")
            return True
        else:
            print("   ❌ Optimizer missing fields.")
            return False
            
    except Exception as e:
        print(f"   ❌ Copycat Logic CRASHED: {e}")
        return False

if __name__ == "__main__":
    # 1. Test Imports & Logic
    v1_logic = test_v1_launch()
    v2_logic = test_v2_launch()
    cc_logic = test_copycat_logic()
    
    # 2. Test Actual Launch (CLI)
    v1_cli = test_cli_launch("nexus_sweeps_tui_v1.py")
    v2_cli = test_cli_launch("nexus_sweeps_tui_v2.py")
    
    if v1_logic and v2_logic and cc_logic and v1_cli and v2_cli:
        print("\n✅ ALL SYSTEMS GO: Full Launch Test Passed.")
        sys.exit(0)
    else:
        print("\n❌ SYSTEM FAILURE: Fix errors above.")
        sys.exit(1)
