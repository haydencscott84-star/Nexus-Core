
TARGET_FILE = "/root/nexus_spreads.py"

DEBUG_LOOKUP_BLOCK = """                # Win % Calculation
                win_val = 0.0
                try:
                    k = f"{s['expiry']}|{short_strike:.1f}"
                    omap = getattr(self, "orats_map", {})
                    orats_dat = omap.get(k, {})
                    
                    # DEBUG LOOKUP
                    try:
                        with open('/tmp/lookup_debug.txt', 'a') as f:
                             if not orats_dat:
                                 # Log only first few misses to avoid spam, or if specific file empty
                                 import os
                                 if os.path.exists('/tmp/lookup_debug.txt') and os.path.getsize('/tmp/lookup_debug.txt') < 5000:
                                     sample_keys = list(omap.keys())[:2] if omap else "EMPTY"
                                     f.write(f"MISS: '{k}' | Map Size: {len(omap)} | Sample: {sample_keys}\\n")
                             else:
                                 f.write(f"HIT: '{k}'\\n")
                    except: pass
                    # END DEBUG
                    
                    iv = orats_dat.get('iv', 0.0)
                    
                    win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                except: pass
"""

def inject_lookup_debug():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # We need to find the block where Win % is calculated
        # It looks like:
        #                 # Win % Calculation
        #                 win_val = 0.0
        #                 try:
        #                     k = f"{s['expiry']}|{short_strike:.1f}"
        
        start_marker = "# Win % Calculation"
        s_idx = content.find(start_marker)
        
        if s_idx == -1:
            print("Error: Win % block not found")
            return

        # Find the end of the try/except block
        # The block ends after the except: pass
        # But we want to replace the inner logic. 
        
        # easier pattern: replace the specific lines
        
        end_marker = "win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)"
        
        e_idx = content.find(end_marker, s_idx)
        if e_idx == -1:
             print("Error: End marker not found")
             return
             
        # Expand end marker to include the line
        e_idx = content.find("\n", e_idx)
        
        # Actually, let's just use string replacement on the block we know exists from previous reads
        
        orig_block = """                # Win % Calculation
                win_val = 0.0
                try:
                    k = f"{s['expiry']}|{short_strike:.1f}"
                    orats_dat = getattr(self, "orats_map", {}).get(k, {})
                    iv = orats_dat.get('iv', 0.0)
                    
                    win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                except: pass"""
        
        if orig_block not in content:
            # Maybe indentation or whitespace differs slightly
            # Let's try to construct it carefully or use regex?
            # Or just replace the retrieval part.
            pass

        # Since we just overwrote it in clean step, we know exactly what it looks like.
        # But let's be safe and replace the chunk from "Win % Calculation" to "except: pass"
        
        regex = r"# Win % Calculation\s+win_val = 0.0\s+try:\s+k = f\"{s\['expiry'\]}\|{short_strike:.1f}\"\s+orats_dat = getattr\(self, \"orats_map\", \{\}\)\.get\(k, \{\}\)\s+iv = orats_dat\.get\('iv', 0.0\)\s+win_val = self\.calculate_pop\(cur_price, be, float\(s\['dte'\]\), iv, strat_type\)\s+except: pass"
        
        import re
        match = re.search(regex, content)
        if match:
             # This is tricky with regex multiline.
             pass
        
        # simpler: find start, find end 'except: pass', slice and replace
        # start: # Win % Calculation
        # end: except: pass (next one)
        
        next_except = content.find("except: pass", s_idx)
        if next_except != -1:
             end_idx = next_except + len("except: pass")
             old_chunk = content[s_idx:end_idx]
             new_content = content.replace(old_chunk, DEBUG_LOOKUP_BLOCK.strip())
             
             with open(TARGET_FILE, 'w') as f:
                 f.write(new_content)
                 print("Lookup Debug Injected.")
        else:
            print("Could not isolate block")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inject_lookup_debug()
