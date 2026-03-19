
import os

target_file = "/root/spx_profiler_nexus.py"
print(f"Applying Real SPX Profiler Optimization (14 Days) to {target_file}...")

updates = [
    ('get_next_n_trading_dates(get_trading_date(), 5)', 
     'get_next_n_trading_dates(get_trading_date(), 14)')
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
            print(f"Patched: {old} -> {new}")
        else:
            print(f"Warning: Could not find target string: {old}")
            
    if count > 0:
        with open(target_file, 'w') as f:
            f.write(new_content)
        print(f"Success! Applied {count} optimizations.")
    else:
        print("No changes applied. File might already be updated.")

except Exception as e:
    print(f"Patch Error: {e}")
