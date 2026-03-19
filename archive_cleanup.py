import os
import glob
import shutil
import re
from datetime import datetime, timedelta
import sys

# Configuration
DATA_SOURCES = {
    'sweeps': 'snapshots_sweeps', 
    'spy': 'snapshots_spy',       
    'spx': 'snapshots'            
}
DAYS_KEEP = 10

def prune_archived_data(days_keep=30):
    print(f"🧹 STARTING PRUNE: Keeping {days_keep} days.")
    base_path = os.getcwd() # Should be /root/
    print(f"   Base Path: {base_path}")
    cutoff_date = (datetime.now() - timedelta(days=days_keep)).date()
    
    total_moved = 0
    
    for source_name, folder in DATA_SOURCES.items():
        full_path = os.path.join(base_path, folder)
        archive_path = os.path.join(full_path, "archive")
        
        if not os.path.exists(full_path):
            print(f"   Skipping {source_name}: Path {full_path} not found.")
            continue
            
        try:
            os.makedirs(archive_path, exist_ok=True)
            print(f"   Checking {source_name} ({full_path})...")
        except Exception as e:
            print(f"   Error creating archive dir: {e}")
            continue
        
        all_files = glob.glob(os.path.join(full_path, "*.csv"))
        print(f"   Found {len(all_files)} CSV files.")
        files_moved = 0
        
        for f in all_files:
            try:
                filename = os.path.basename(f)
                match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                if match:
                    file_date = datetime.strptime(match.group(1), "%Y-%m-%d").date()
                    if file_date < cutoff_date:
                        # Move to archive
                        shutil.move(f, os.path.join(archive_path, filename))
                        files_moved += 1
                        if files_moved % 1000 == 0:
                            print(f"      Moved {files_moved} files...")
            except Exception as e:
                print(f"   Error archiving {f}: {e}")
                
        if files_moved > 0:
            print(f"🧹 [Maintenance] Archived {files_moved} old files from {source_name}")
            total_moved += files_moved
        else:
            print(f"   No files to archive in {source_name}")
            
    print(f"✅ CLEANUP COMPLETE. Total moved: {total_moved}")

if __name__ == "__main__":
    prune_archived_data(DAYS_KEEP)
