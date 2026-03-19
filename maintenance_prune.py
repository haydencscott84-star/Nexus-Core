from analyze_snapshots import prune_archived_data

print("🚀 FORCE RUNNING MAINTENANCE...")
try:
    prune_archived_data(days_keep=30)
    print("✅ Maintenance Complete.")
except Exception as e:
    print(f"❌ Maintenance Failed: {e}")
