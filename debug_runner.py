
import sys
import os
import asyncio
# Mock textual app context if needed
from analyze_snapshots import StrategicHUD

async def run_debug():
    print("--- STARTING HEADLESS DEBUG ---")
    app = StrategicHUD()
    
    print("1. Fetching SPY Data (Internal Method)...")
    # This calls the method I patched with Mibian fallback
    try:
        # We need to manually trigger the fetch logic usually inside fetch_and_save_snapshots
        # But fetch_and_save_snapshots is complex.
        # Let's call get_orats_data directly first to check raw API return
        strikes = app.get_orats_data('strikes')
        print(f"   Raw Strikes Returned: {len(strikes)}")
        if strikes: # Print sample
             print(f"   Sample Key Check: {list(strikes[0].keys())}")
             atm = [s for s in strikes if 680 <= float(s.get('strike')) <= 685]
             if atm:
                 print(f"   ATM Raw: {atm[0]}")
    except Exception as e:
        print(f"   [ERROR] get_orats_data failed: {e}")

    print("\n2. Testing Mibian Import...")
    try:
        import mibian
        print("   Mibian Imported Successfully.")
    except ImportError:
        print("   [ERROR] Mibian NOT found.")

    print("\n3. Testing Logic (Dry Run)...")
    # I want to trigger the loop in fetch_and_save_snapshots lines 640+
    # But that method updates self.traps_df and calls enrich_traps...
    # It's hard to isolate without running the whole app.
    # But I can inspect the code I edited:
    # It was inside fetch_and_save_snapshots.
    
    print("--- DEBUG COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(run_debug())
