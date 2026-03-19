
# PATCH FORCE INDENT
# Normalizes indentation for the entire file to fixing persistent errors.

import re

FILE = "nexus_debit_downloaded.py"

def normalize():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    new_lines = []
    class_started = False
    
    for line in lines:
        # 1. Expand tabs
        s_line = line.expandtabs(4)
        stripped = s_line.strip()
        
        # Check class start
        if stripped.startswith("class DebitSniperApp"):
            class_started = True
            new_lines.append(s_line) # Keep as is (likely 0 indent)
            continue
            
        if not class_started:
            new_lines.append(s_line)
            continue
            
        # Inside class, normalize method definitions
        # Methods should have 4 spaces.
        if stripped.startswith("def ") or stripped.startswith("async def "):
            # Force 4 spaces
            new_lines.append("    " + stripped + "\n")
            continue
            
        # Decorators inside class
        if stripped.startswith("@on("):
            new_lines.append("    " + stripped + "\n")
            continue
            
        # Preserve other lines (hope their relative indent is ok)
        # But we must ensure they are at least 8 spaces if inside a method?
        # Too risky to touch all lines.
        # But the error 'unindent does not match' often comes from a line having 3 spaces or 5.
        
        # Just appending s_line (expanded tabs) usually fixes it unless mixed.
        new_lines.append(s_line)
        
    with open(FILE, 'w') as f: f.writelines(new_lines)
    print("Forced method indentation.")

if __name__ == "__main__":
    normalize()
