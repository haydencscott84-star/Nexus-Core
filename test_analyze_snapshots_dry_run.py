
import sys
import os

# Ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("🚀 Starting Dry Run Analyzer...")

try:
    # 1. Test Headless Import
    from analyze_snapshots import run_headless_analysis, load_unified_data
    print("✅ Logic Imported.")
    
    # 2. Mock 'nexus_history.json' dumper to avoid writing to disk in test
    import analyze_snapshots
    def mock_dump(f, d):
        print(f"✅ Would write to {f}: {list(d.keys())}")
    analyze_snapshots.antigravity_dump = mock_dump
    
    # 3. Test One Cycle of Logic
    # We break the loop by mocking time.sleep to raise an exception we catch
    original_sleep = analyze_snapshots.time.sleep
    def mock_sleep(sec):
        raise KeyboardInterrupt("Test Complete")
    analyze_snapshots.time.sleep = mock_sleep
    
    print("🏃 Running Logic Cycle (CTRL+C simulated)...")
    try:
        run_headless_analysis()
    except KeyboardInterrupt:
        print("🏁 Dry Run Cycle Finished Successfully.")
    finally:
        analyze_snapshots.time.sleep = original_sleep
        
except Exception as e:
    print(f"❌ CRASHED: {e}")
    import traceback
    traceback.print_exc()
