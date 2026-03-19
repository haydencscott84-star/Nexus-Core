
import pandas as pd
import glob
import os

DATA_SOURCES = {
    'sweeps': 'snapshots_sweeps', 
    'spy': 'snapshots_spy',       
    'spx': 'snapshots'            
}

def inspect_headers():
    base_path = os.getcwd()
    print(f"Base Path: {base_path}")
    
    for source_name, folder in DATA_SOURCES.items():
        print(f"\n--- Checking Source: {source_name} (Folder: {folder}) ---")
        full_path = os.path.join(base_path, folder)
        
        if not os.path.exists(full_path):
            print(f"Folder not found: {full_path}")
            continue
            
        csv_files = glob.glob(os.path.join(full_path, "*.csv"))
        if not csv_files:
            print(f"No CSV files found in {full_path}")
            continue
            
        # Pick the most recent one just to be relevant
        csv_files.sort(key=os.path.getmtime, reverse=True)
        target_file = csv_files[0]
        print(f"Inspecting File: {os.path.basename(target_file)}")
        
        try:
            df = pd.read_csv(target_file, nrows=1)
            print("Columns:")
            print(df.columns.tolist())
            print("First Row Data:")
            print(df.iloc[0].to_dict())
        except Exception as e:
            print(f"Error reading file: {e}")

if __name__ == "__main__":
    inspect_headers()
