
# PATCH CSS FIX: FORCE VERTICAL LAYOUT
# Targets: nexus_debit_downloaded.py, nexus_spreads_downloaded.py

DEBIT = "nexus_debit_downloaded.py"
SPREADS = "nexus_spreads_downloaded.py"

# New CSS for Vertical Stack
# 1. layout: vertical
# 2. children height: 1fr (50% each)
CSS_VERTICAL = r'''
    /* BOTTOM PANE: POSITIONS & LOG */
    #bottom_container {
        row-span: 1;
        column-span: 1;
        layout: vertical;
        /* Removed grid-columns */
    }
    
    #positions_table {
        border-top: solid #444;
        height: 1fr;
        width: 100%;
    }
    
    #activity_log {
        border-top: solid #444;
        height: 1fr;
        width: 100%;
        background: #000;
        overflow-x: auto;
    }
'''

def patch_file(path, label="DEBIT"):
    with open(path, 'r') as f: content = f.read()
    
    # We replace the entire block from #bottom_container to #activity_log end
    # Need markers
    start_marker = "    /* BOTTOM PANE: POSITIONS & LOG */"
    end_marker = "    /* EXECUTION WIDGETS */"
    
    if start_marker in content and end_marker in content:
        pre, post = content.split(start_marker, 1)
        body, remainder = post.split(end_marker, 1)
        
        # Build new content
        # Note: CSS_VERTICAL has indentation? 
        # The variables in Python are indented in the class string.
        # We need to ensure we don't break the string structure.
        # The CSS is likely inside a VARIABLE = """ ... """ block.
        # Let's clean up the CSS_VERTICAL to align.
        
        final = pre + CSS_VERTICAL + "\n    " + end_marker + remainder
        with open(path, 'w') as f: f.write(final)
        print(f"Patched {label}: {path}")
    else:
        print(f"Markers not found in {label}")
        # Debug
        if start_marker not in content: print(f"  Missing start: {start_marker.strip()}")
        if end_marker not in content: print(f"  Missing end: {end_marker.strip()}")

if __name__ == "__main__":
    patch_file(DEBIT, "DEBIT")
    patch_file(SPREADS, "SPREADS")
