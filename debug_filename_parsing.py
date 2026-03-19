import os
import glob
from datetime import datetime

# Mock Data Sources
DATA_SOURCES = {
    'sweeps': 'snapshots_sweeps', 
    'spy': 'snapshots_spy',       
    'spx': 'snapshots'            
}

def test_parsing():
    base_path = os.getcwd()
    print(f"Base Path: {base_path}")
    
    for source_name, folder in DATA_SOURCES.items():
        full_path = os.path.join(base_path, folder)
        if not os.path.exists(full_path):
            print(f"Skipping {folder} (Not found)")
            continue
            
        print(f"\nScanning {folder}...")
        all_files = sorted(glob.glob(os.path.join(full_path, "*.csv")))
        print(f"Found {len(all_files)} files.")
        
        for f in all_files[:5]: # Check first 5
            filename = os.path.basename(f)
            print(f"  File: {filename}")
            
            # Proposed Regex Logic
            import re
            try:
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    date_str = match.group(1)
                    print(f"    Regex Match: '{date_str}'")
                    dt = datetime.strptime(date_str, "%Y-%m-%d")
                    print(f"    ✅ Parsed: {dt.date()}")
                else:
                    print(f"    ❌ No Date Pattern Found")
            except Exception as e:
                print(f"    ❌ Parse Failed ({e})")

if __name__ == "__main__":
    test_parsing()
