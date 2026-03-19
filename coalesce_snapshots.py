
import os
import json
import glob

# Config
SOURCE_DIR = "/Users/haydenscott/Desktop/snapshots_backup/root/snapshots"
OUTPUT_FILE = "/Users/haydenscott/Desktop/snapshots_overview.json"

def main():
    print(f"Scanning {SOURCE_DIR}...")
    
    # Get List of JSONs
    files = glob.glob(os.path.join(SOURCE_DIR, "*.json"))
    files.sort() # Sort by filename (which is date-prefixed, so chronological)
    
    master_data = []
    
    print(f"Found {len(files)} snapshots. Merging...")
    
    for f_path in files:
        try:
            fname = os.path.basename(f_path)
            
            with open(f_path, 'r') as f:
                content = json.load(f)
                
            # Create a structured entry
            entry = {
                "source_file": fname,
                "snapshot_data": content
            }
            master_data.append(entry)
            print(f"Processed: {fname}")
            
        except Exception as e:
            print(f"Error reading {f_path}: {e}")

    # Write Output
    try:
        print(f"Writing {len(master_data)} records to {OUTPUT_FILE}...")
        with open(OUTPUT_FILE, 'w') as out:
            json.dump(master_data, out, indent=2)
        print("Success!")
        
    except Exception as e:
        print(f"Error writing output: {e}")

if __name__ == "__main__":
    main()
