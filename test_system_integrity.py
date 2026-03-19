import sys
import os

print("🔍 Starting System Integrity Check...")

modules_to_test = [
    "gemini_market_auditor",
    "analyze_snapshots",
    "spx_profiler_nexus",
    "spy_profiler_nexus_v2",
    "backtest_reversion_pro",
    "backtest_reversion_hourly",
    "structure_nexus"
]

failed = []

for mod in modules_to_test:
    try:
        print(f"Checking {mod}...", end=" ")
        __import__(mod)
        print("✅ OK")
    except Exception as e:
        print(f"❌ FAILED: {e}")
        failed.append(mod)

if failed:
    print(f"\n⚠️ Integrity Issues Found in: {', '.join(failed)}")
    sys.exit(1)
else:
    print("\n✅ ALL SYSTEMS GREEN. Integrity Verified.")
    sys.exit(0)
