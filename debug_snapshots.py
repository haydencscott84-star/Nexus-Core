import os
import glob
import pandas as pd
from datetime import datetime

SNAPSHOT_DIR = "snapshots_sweeps"

print(f"--- DEBUGGING SNAPSHOTS ---")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Looking for folder: {os.path.join(os.getcwd(), SNAPSHOT_DIR)}")

if not os.path.exists(SNAPSHOT_DIR):
    print(f"❌ ERROR: Folder '{SNAPSHOT_DIR}' does not exist!")
else:
    print(f"✅ Folder found.")
    
    # Check for files
    pattern = os.path.join(SNAPSHOT_DIR, "*_sweeps_flow.csv")
    files = sorted(glob.glob(pattern))
    
    print(f"Found {len(files)} CSV files matching pattern: {pattern}")
    
    if len(files) == 0:
        # Check if there are ANY files (maybe named differently?)
        all_files = os.listdir(SNAPSHOT_DIR)
        print(f"Contents of directory: {all_files}")
    else:
        # Try to load the most recent file
        latest_file = files[-1]
        print(f"\nAttempting to read latest file: {latest_file}")
        
        try:
            # 1. Check Filename parsing
            base = os.path.basename(latest_file)
            print(f"Filename: {base}")
            date_part = base.split("_")[0]
            print(f"Parsed Date Part: '{date_part}'")
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            print(f"✅ Date valid: {dt}")
            
            # 2. Check CSV Content
            df = pd.read_csv(latest_file)
            print(f"✅ CSV Loaded. Rows: {len(df)}")
            print(f"Columns found: {list(df.columns)}")
            
            # 3. Check Premium Logic (The Filter)
            if 'total_premium' in df.columns:
                total_flow = df['total_premium'].sum()
                print(f"Total Premium in file: ${total_flow:,.2f}")
            else:
                print("❌ CRITICAL: 'total_premium' column missing!")
                
            # 4. Check Open Interest (For Freshness)
            if 'open_interest' in df.columns:
                print("✅ 'open_interest' column exists.")
            else:
                print("⚠️ WARNING: 'open_interest' missing. (Did you update the recorder script?)")

        except Exception as e:
            print(f"❌ ERROR Reading File: {e}")

print("\n---------------------------")