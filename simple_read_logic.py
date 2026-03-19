
import sys
try:
    with open('/root/nexus_spreads.py', 'r') as f:
        lines = f.readlines()
        
    target_line = -1
    for i, line in enumerate(lines):
        if 'self.managed_spreads[s_sym] =' in line:
            target_line = i
            break
            
    if target_line != -1:
        start = max(0, target_line - 60)
        end = min(len(lines), target_line + 20)
        print("___START_CODE___")
        for j in range(start, end):
            print(f"{j+1}: {lines[j].rstrip()}")
        print("___END_CODE___")
    else:
        print("TARGET_NOT_FOUND")
        
except Exception as e:
    print(f"ERROR: {e}")
