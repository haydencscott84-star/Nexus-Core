import os, sys, glob, re, time
from datetime import datetime, timedelta
import pandas as pd

DATA_SOURCES = {'spy': 'snapshots_spy', 'spx': 'snapshots'}
days_back = 5
base_path = os.getcwd()

cutoff = (datetime.now() - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
print(f"Loading files since: {cutoff}")

total_rows = 0
start_t = time.time()

for source_name, folder in DATA_SOURCES.items():
    full_path = os.path.join(base_path, folder)
    all_files = sorted(glob.glob(os.path.join(full_path, "*.csv")))
    latest_files_map = {}
    
    for f in all_files:
        try:
            filename = os.path.basename(f)
            match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if match:
                date_str = match.group(1)
                latest_files_map[date_str] = f
        except: pass

    sorted_dates = sorted(latest_files_map.keys())
    if len(sorted_dates) > 50:
        sorted_dates = sorted_dates[-50:]
        
    unique_files = [latest_files_map[d] for d in sorted_dates]
    print(f"[{source_name}] Found {len(unique_files)} unique date files to check.")
    
    for f in unique_files:
        filename = os.path.basename(f)
        match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
        if not match: continue
        
        file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
        if file_date >= cutoff:
            print(f"Loading {filename}...", end=" ")
            try:
                df = pd.read_csv(f)
                total_rows += len(df)
                print(f"({len(df)} rows)")
            except Exception as e:
                print(f"FAILED: {e}")

print(f"\nDone! Processed {total_rows} rows in {time.time() - start_t:.2f}s")
