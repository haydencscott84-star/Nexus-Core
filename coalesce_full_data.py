
import os
import json
import glob

# Config
SOURCE_ROOT = "/Users/haydenscott/Desktop/all_data_export"
OUTPUT_FILE = "/Users/haydenscott/Desktop/comprehensive_market_data.json"

def main():
    print(f"Scanning {SOURCE_ROOT} recursively...")
    
    # We need to find all .json files in the subdirectories
    # The tar structure is likely:
    # root/snapshots/*.json
    # root/snapshots_spy/*.json
    
    # Use glob with recursive search
    files = glob.glob(os.path.join(SOURCE_ROOT, "**/*.json"), recursive=True)
    files.sort()
    
    master_data = []
    
    print(f"Found {len(files)} files. Merging...")
    
    for f_path in files:
        try:
            fname = os.path.basename(f_path)
            parent_dir = os.path.basename(os.path.dirname(f_path))
            
            # Determine Ticker based on folder
            if "snapshots_spy" in parent_dir or "spy" in fname.lower():
                ticker = "SPY"
            elif "snapshots" == parent_dir: # Default folder is usually SPX
                ticker = "SPX"
            elif "sweeps" in parent_dir:
                ticker = "SWEEPS"
            else:
                ticker = "UNKNOWN"
            
            with open(f_path, 'r') as f:
                content = json.load(f)
                
            # Create a structured entry
            entry = {
                "source_file": fname,
                "folder": parent_dir,
                "ticker": ticker,
                "data": content
            }
            master_data.append(entry)
            print(f"[{ticker}] Processed: {fname}")
            
        except Exception as e:
            print(f"Error reading {f_path}: {e}")

    # Write Output
    try:
        print(f"Writing {len(master_data)} records to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as out:
            json.dump(master_data, out, indent=2)
        print("Success! Data Consolidation Complete.")
        
    except Exception as e:
        print(f"Error writing output: {e}")

if __name__ == "__main__":
    main()
