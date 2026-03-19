
# PATCH WHITESPACE FIX
import re

FILE = "nexus_debit_downloaded.py"

def fix_whitespace():
    with open(FILE, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    for line in lines:
        # 1. Expand tabs
        l = line.expandtabs(4)
        new_lines.append(l)
        
    # Re-process to fix specific methods that might be unindented
    final_lines = []
    for i, line in enumerate(new_lines):
        # Fix populate_debit_chain if unindented
        if line.startswith("def populate_debit_chain(self,"):
            # Indent it
            final_lines.append("    " + line)
            print("Indented populate_debit_chain")
            continue
            
        # Fix async def fetch_chain if unindented
        if line.startswith("async def fetch_chain(self)"):
             final_lines.append("    " + line)
             print("Indented fetch_chain")
             continue

        final_lines.append(line)
        
    with open(FILE, 'w') as f:
        f.writelines(final_lines)
        
    print(f"Whitespace normalized for {len(final_lines)} lines.")

if __name__ == "__main__":
    fix_whitespace()
