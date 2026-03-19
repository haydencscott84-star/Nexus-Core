
TARGET_FILE = "/root/nexus_spreads.py"

# We will search for the specific block and replace it.
# The block starts with "# Win % Calculation" and ends at the except block.

NEW_LOGIC = """                # Win % Calculation
                win_val = 0.0
                try:
                    # Robust Key Generation (Try both .1f and int if applicable)
                    k_float = f"{s['expiry']}|{float(short_strike):.1f}"
                    # If strike is effectively an int (e.g. 672.0), try key '...|672' too
                    k_int = f"{s['expiry']}|{int(short_strike)}"
                    
                    omap = getattr(self, "orats_map", {})
                    orats_dat = omap.get(k_float)
                    if not orats_dat:
                        orats_dat = omap.get(k_int)
                    
                    # DEBUG LOGGING (First few misses)
                    if not orats_dat:
                        try:
                            import os
                            log_file = '/tmp/nexus_win_debug.log'
                            if not os.path.exists(log_file) or os.path.getsize(log_file) < 10000:
                                with open(log_file, 'a') as f:
                                    debug_keys = list(omap.keys())[:3] if omap else "EMPTY_MAP"
                                    f.write(f"MISS: Tried '{k_float}' / '{k_int}' | Map Size: {len(omap)} | Sample: {debug_keys}\\n")
                        except: pass
                    
                    if orats_dat:
                         iv = orats_dat.get('iv', 0.0)
                         win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                except:
                    pass
"""

def apply_fix():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Identify the start and end of the block to replace
        start_marker = "# Win % Calculation"
        
        # We need to find where the `try... except` block for Win% ends.
        # It ends with `except: pass` (or `except Exception...`)
        # then typically followed by `if win_val == 0:`
        
        s_idx = content.find(start_marker)
        if s_idx == -1:
            # Fallback search if comments stripped or changed
            s_idx = content.find('win_val = 0.0')
            if s_idx == -1:
                print("Error: Could not find Win% block start")
                return
        
        # Determine end of block
        # Look for the line: `if win_val == 0: win_str = "-"`
        end_marker = 'if win_val == 0: win_str = "-"'
        e_idx = content.find(end_marker, s_idx)
        
        if e_idx == -1:
             # Try variant
             end_marker = 'if win_val == 0:'
             e_idx = content.find(end_marker, s_idx)
        
        if e_idx == -1:
            print("Error: Could not find Win% block end")
            return

        # Replace the chunk
        # Note: NEW_LOGIC ends with newline, we want to butt up against `if win_val...`
        # We need to preserve indentation of NEW_LOGIC (16 spaces based on previous file reads)
        # The replacement block provided above has 16 spaces indentation.
        
        # Let's verify indentation of file
        # Find newline before s_idx
        nl_prev = content.rfind('\n', 0, s_idx)
        indent = content[nl_prev+1:s_idx]
        # We can adjust NEW_LOGIC if needed, but it looks like 16 spaces is standard for this depth
        
        old_chunk = content[s_idx:e_idx]
        
        # Check if we need to clean up extra newlines
        
        new_content = content[:s_idx] + NEW_LOGIC.strip() + "\n                " + content[e_idx:]
        # The + "\n                " is to align the `if win_val` line if we stripped it?
        # No, NEW_LOGIC.strip() removes trailing whitespace from our string.
        # But we want to ensure `if win_val` starts on a new line with correct indentation.
        # content[e_idx:] starts with `if win_val...`. 
        # So we need a newline and indentation before it.
        # `if win_val` is at indentation level 16 typically.
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Win% Lookup Fix Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_fix()
