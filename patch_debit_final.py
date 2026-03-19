
import re

# PATCH FINAL: Fix Indentation & Win% (Broad Net)
TARGET_FILE = "/root/nexus_debit.py"

def apply_final_fix():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # We will replace the entire loop block to ensure indentation is perfect.
        # We start matching from the loop header.
        
        # Original indentation context:
        # 623: def populate_debit_chain...
        # 624:     try:
        # ...
        # 643:             for s in chain_data:
        
        # So we need 12 spaces for the loop header.
        
        # We will construct a regex that matches the broken loop header and the first few lines
        # "for s in chain_data:" ... up to "ask_short ="
        
        regex = r'(^\s*)for s in chain_data:.*?ask_short ='
        
        # New block with Broad Net Logic for Win%
        # We put the "Broad Net" calc *inside* the loop (later), but here we just fix the header.
        # Wait, the Win% logic is further down in the loop.
        # I need to replace the header to fix indentation, AND replace the Win% logic.
        
        # 1. FIX HEADER INDENTATION
        # We replace the broken header with a clean one.
        # We use strict 12 spaces.
        
        clean_header = """            for s in chain_data:
                 ask_short ="""
        
        if re.search(regex, content, re.DOTALL | re.MULTILINE):
            content = re.sub(regex, clean_header, content, count=1, flags=re.DOTALL | re.MULTILINE)
            print("Header Indentation Fixed.")
        
        # 2. UPDATE WIN% LOGIC (Broad Net)
        # We look for the win_pct block we added earlier.
        # It looked like:
        # l_delta = 0.0
        # try:
        #    if 'greeks' in s: ...
        
        win_regex = r'l_delta = 0\.0.*?win_str = f"\{abs\(l_delta\*100\):\.0f\}%"'
        
        new_win_logic = """l_delta = 0.0
                 try:
                     # Broad Net for Delta
                     if 'greeks' in s: l_delta = float(s['greeks'].get('delta', 0))
                     elif 'delta' in s: l_delta = float(s['delta'])
                     elif 'long_leg' in s: l_delta = float(s['long_leg'].get('greeks',{}).get('delta',0))
                     elif 'long' in s and isinstance(s['long'], dict): l_delta = float(s['long'].get('delta', 0))
                 except: pass
                 
                 win_str = f"{abs(l_delta*100):.0f}%\""""
                 
        if re.search(win_regex, content, re.DOTALL):
            content = re.sub(win_regex, new_win_logic, content, count=1, flags=re.DOTALL)
            print("Win% Logic Updated (Broad Net).")
        else:
            print("Win% Logic NOT FOUND (Regex mismatch).")

        with open(TARGET_FILE, 'w') as f:
            f.write(content)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_final_fix()
