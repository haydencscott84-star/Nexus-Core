import pandas as pd
import glob
import os
import re

def test_load():
    # Simulate loading the latest SPY file
    full_path = "/root/snapshots_spy"
    all_files = sorted(glob.glob(os.path.join(full_path, "*.csv")))
    if not all_files:
        print("No files found!")
        return

    f = all_files[-1]
    print(f"Loading: {f}")
    
    df = pd.read_csv(f)
    print(f"Columns: {df.columns.tolist()}")
    
    # Check DTE 15 / Strike 680
    mask = (df['stk'] == 680) & (df['dte'] == 15) & (df['type'] == 'CALL')
    row = df[mask]
    
    if not row.empty:
        print("RAW ROW:")
        print(row[['stk','dte','gamma','vega','theta']])
        
        # Test cleaning logic
        if 'theta' in df.columns:
            val = pd.to_numeric(df['theta'], errors='coerce').fillna(0)
            print(f"Parsed Theta Series Mean: {val.mean()}")
            print(f"Row Theta Value: {val[row.index[0]]}")
    else:
        print("Row not found! Dumping similar rows:")
        print(df[(df['stk']==680) & (df['type']=='CALL')][['stk','dte','gamma','vega','theta']].head())

if __name__ == "__main__":
    test_load()
