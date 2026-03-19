
import os

target_file = "/root/analyze_snapshots.py"
print(f"Reverting SPX Profiler Optimization (Back to 10 Days) to {target_file}...")

updates = [
    # 1. Revert Background Loader Call
    ('await loop.run_in_executor(None, load_unified_data, 14, None)', 
     'await loop.run_in_executor(None, load_unified_data, 10, None)'),
     
    # 2. Revert Log Message
    ('self.log_msg("⏳ Loading 14-Day History in Background...")', 
     'self.log_msg("⏳ Loading 10-Day History in Background...")'),
     
    # 3. Revert Narrative Default
    ('def generate_expiry_narrative(df, days_back=14):', 
     'def generate_expiry_narrative(df, days_back=10):')
]

try:
    with open(target_file, 'r') as f:
        content = f.read()
        
    new_content = content
    count = 0
    
    for old, new in updates:
        if old in new_content:
            new_content = new_content.replace(old, new)
            count += 1
            print(f"Reverted: {old} -> {new}")
        else:
            print(f"Warning: Could not find target string: {old}")
            
    if count > 0:
        with open(target_file, 'w') as f:
            f.write(new_content)
        print(f"Success! Reverted {count} changes.")
    else:
        print("No changes needed. File might already be reverted.")

except Exception as e:
    print(f"Revert Error: {e}")
