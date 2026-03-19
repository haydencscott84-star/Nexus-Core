
TARGET_FILE = "/root/nexus_debit.py"

NEW_BLOCK = """                    # Win % (PoP Logic)
                    win_pct = 0.0
                    try:
                        # Robust Key Generation
                        k_float = f"{s['expiry']}|{float(l_strike):.1f}"
                        k_int = f"{s['expiry']}|{int(l_strike)}"
                        
                        omap = getattr(self, "orats_map", {})
                        orats_data = omap.get(k_float)
                        if not orats_data:
                            orats_data = omap.get(k_int, {})
                        
                        # VERBOSE LOGGING
                        try:
                            import os
                            log_file = '/tmp/debit_verbose.log'
                            if not os.path.exists(log_file) or os.path.getsize(log_file) < 50000:
                                with open(log_file, 'a') as f:
                                    hit = "HIT" if orats_data else "MISS"
                                    iv_val = orats_data.get('iv', -1) if orats_data else -1
                                    # Use be, strat_type, cur_price from scope
                                    f.write(f"{hit}: Float='{k_float}' Int='{k_int}' | IV={iv_val} | Strat={strat_type} | BE={be:.2f} | Spot={cur_price}\\n")
                        except: pass

                        if isinstance(orats_data, float): orats_data = {'delta': orats_data, 'iv': 0.0}
                        
                        iv = orats_data.get('iv', 0.0)
                        win_pct = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                    except: pass
"""

def fix_debit_lookup_verbose():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Identify block to replace
        start_marker = '# Win % (PoP Logic)'
        s_idx = content.find(start_marker)
        if s_idx == -1:
            print("Error: Start marker not found")
            return

        # Find line `if isinstance(orats_data, float):` to locate end
        end_marker = "if isinstance(orats_data, float): orats_data = {'delta': orats_data, 'iv': 0.0}"
        e_idx = content.find(end_marker, s_idx)
        
        if e_idx == -1:
             print("Error: End marker not found")
             return
             
        # Find newline after end_marker (to include it in replacement since NEW_BLOCK has it)
        e_idx_end = content.find('\n', e_idx)
        if e_idx_end == -1: e_idx_end = len(content)
        
        new_content = content[:s_idx] + NEW_BLOCK + content[e_idx_end:]
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Debit Win% Verbose Fix Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_debit_lookup_verbose()
