
import re

# PATCH: Add WIN% Column to Nexus Debit
# Targets: nexus_debit.py
# 1. Update Columns: "L. DELTA" -> "WIN %"
# 2. Update Logic: Replace l_delta raw display with f"{abs(l_delta*100):.0f}%"

FILE_PATH = "/root/nexus_debit.py"

def patch_debit_columns():
    try:
        with open(FILE_PATH, 'r') as f:
            content = f.read()

        # 1. REPLACE COLUMN HEADER
        # Old: "L. DELTA"
        # New: "WIN %"
        if '"L. DELTA"' in content:
            content = content.replace('"L. DELTA"', '"WIN %"')
            print(f"Header Patched: WIN %")
        else:
            print("Header NOT FOUND or already patched.")

        # 2. REPLACE ROW LOGIC
        # We need to find where the row is constructed.
        # It looks like:
        # [..., Text(f"{max_roc:.1f}%", style=roc_style), f"{l_delta:.2f}"]
        
        # Regex to find the row construction block
        # We look for the line adding l_delta to the row list
        
        # Pattern matching the specific list element
        old_pattern = r'f"\{l_delta:.2f\}"'
        new_pattern = r'f"{abs(l_delta*100):.0f}%"'
        
        if re.search(old_pattern, content):
            content = re.sub(old_pattern, new_pattern, content)
            print("Row Logic Patched: Win % Calc")
        else:
            print("Row Logic pattern NOT FOUND (might be diff format).")
            # Fallback check if it's just l_delta without format
            if 'f"{l_delta}"' in content:
                 content = content.replace('f"{l_delta}"', 'f"{abs(l_delta*100):.0f}%"')
                 print("Row Logic Patched (Fallback)")

        with open(FILE_PATH, 'w') as f:
            f.write(content)
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    patch_debit_columns()
