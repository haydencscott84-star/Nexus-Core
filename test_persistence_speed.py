import time
from analyze_snapshots import load_unified_data, analyze_persistence

print("Loading Data...")
t0 = time.time()
df = load_unified_data(5)
print(f"Loaded {len(df)} rows in {time.time()-t0:.2f}s")

print("Running analyze_persistence...")
t1 = time.time()
stats = analyze_persistence(df)
print(f"Persistence finished in {time.time()-t1:.2f}s with {len(stats)} rows")
