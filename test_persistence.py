import os, sys, glob, re, time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

DATA_SOURCES = {'spy': 'snapshots_spy', 'spx': 'snapshots'}
days_back = 5
base_path = os.getcwd()
cutoff = (datetime.now() - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)

master_dfs = []
for source_name, folder in DATA_SOURCES.items():
    full_path = os.path.join(base_path, folder)
    all_files = sorted(glob.glob(os.path.join(full_path, "*.csv")))
    latest_files_map = {}
    for f in all_files:
        try:
            filename = os.path.basename(f)
            match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if match: latest_files_map[match.group(1)] = f
        except: pass
        
    sorted_dates = sorted(latest_files_map.keys())[-50:]
    unique_files = [latest_files_map[d] for d in sorted_dates]
    
    for f in unique_files:
        filename = os.path.basename(f)
        match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
        if not match: continue
        file_date = datetime.strptime(match.group(1), "%Y-%m-%d")
        if file_date >= cutoff:
            df = pd.read_csv(f)
            std_df = pd.DataFrame(index=df.index)
            std_df['date'] = file_date
            std_df['ticker'] = source_name.upper()
            std_df['strike'] = pd.to_numeric(df.get('stk', df.get('strike', 0)), errors='coerce')
            std_df['oi'] = pd.to_numeric(df.get('oi', df.get('open_interest', 0)), errors='coerce').fillna(0)
            std_df['premium'] = pd.to_numeric(df.get('prem', df.get('total_premium', 0)), errors='coerce').fillna(0)
            std_df['is_bull'] = df.get('conf', pd.Series([''] * len(df))).astype(str).str.contains("BULL")
            master_dfs.append(std_df)

print(f"DataFrames loaded: {len(master_dfs)}")
master = pd.concat(master_dfs, ignore_index=True)
print(f"Master concat complete: {len(master)} rows")

# --- Test analyze_persistence ---
print("Running analyze_persistence...")
start_t = time.time()
df = master.copy()

# Sort by Date
df = df.sort_values('date').reset_index(drop=True)

# Group by Strike and Ticket
print("Grouping...")
grouped = df.groupby(['ticker', 'strike'])

records = []
for name, group in grouped:
    group = group.sort_values('date')
    if len(group) > 1:
        first_oi = group.iloc[0]['oi']
        last_oi = group.iloc[-1]['oi']
        oi_delta = last_oi - first_oi
        records.append({
            'ticker': name[0],
            'strike': name[1],
            'last_date': group.iloc[-1]['date'],
            'initial_oi': first_oi,
            'current_oi': last_oi,
            'oi_delta': oi_delta,
            'total_bull_prem': group[group['is_bull']]['premium'].sum(),
            'total_bear_prem': group[~group['is_bull']]['premium'].sum()
        })

stats_df = pd.DataFrame(records)
print(f"analyze_persistence finished in {time.time() - start_t:.2f}s. Rows: {len(stats_df)}")
