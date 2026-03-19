
# REPAIR INDENTATION FOR NEXUS SPREADS
# Target: nexus_spreads_downloaded.py
# Problem: Replaced 'if match:' block lost its indentation for the body.

FILE = "nexus_spreads_downloaded.py"

def repair():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    # Range to repair: Lines 423 to ... roughly 460?
    # Based on view: 
    # 422: if match:
    # 423: l = match (Needs Indent)
    # ...
    # 465: processed_syms.add(l["sym"]) (Needs Indent)
    # 466: DATA SYNC... (Needs Indent)
    # End of block is where?
    # The next block in the file (from previous view) was line 447 "async def fetch_managed_spreads_loop".
    # Wait, my previous read showed line 447 as "UI: Add Row".
    # Let's target lines from 423 matching specific content and indent them if they start with a char.
    
    new_lines = []
    in_block = False
    
    for i, line in enumerate(lines):
        # Trigger start
        if "if match:" in line and i > 415: # Roughly locate the right one
            in_block = True
            new_lines.append(line)
            continue
            
        if in_block:
            # Check if we hit the end of the method/loop
            if "async def" in line or "class " in line or "def " in line:
                in_block = False
                new_lines.append(line)
                continue
                
            # If line is not empty and not already indented enough?
            # The corrupted lines looked like "l = match" (0 indent or 16 indent? original was deep).
            # The 'if match:' is at... let's count spaces.
            # line 408: '            for s in shorts:' (12 chars)
            # line 422: '                if match:' (16 chars)
            # So body needs 20 spaces.
            # Currently it likely has 16 or fewer if replaced badly.
            # Line 423: 'l = match' (captured as '                l = match' in the view? No, view shows numbering.)
            # The view showed:
            # 422:                 if match:
            # 423:                 l = match
            # They aligned!
            # So line 423 has 16 spaces. It needs 20.
            
            stripped = line.lstrip()
            if not stripped: 
                new_lines.append(line) # Keep blank lines
                continue
                
            current_indent = len(line) - len(stripped)
            if current_indent == 16:
                # Add 4 spaces
                new_lines.append("    " + line)
            else:
                # Assuming correct or outer scope
                new_lines.append(line)
        else:
            new_lines.append(line)
            
    with open(FILE, 'w') as f: f.writelines(new_lines)
    print("Repaired Indentation in Nexus Spreads.")

if __name__ == "__main__":
    repair()
