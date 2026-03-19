from analyze_snapshots import load_unified_data

print("🚀 Running History Debugger...")
df = load_unified_data(5)

if df.empty:
    print("❌ No data loaded.")
else:
    print(f"✅ Loaded {len(df)} rows.")
