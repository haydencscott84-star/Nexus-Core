import time
import analyze_snapshots
from analyze_snapshots import load_unified_data

print("Starting Load Benchmark (10 days)...")
start = time.time()

# Mock log function
def log(msg):
    print(f"[LOG] {msg}")

try:
    df = load_unified_data(10, log_func=log)
    end = time.time()
    print(f"DONE. loaded {len(df)} rows in {end - start:.2f} seconds")
except Exception as e:
    print(f"CRASH: {e}")
