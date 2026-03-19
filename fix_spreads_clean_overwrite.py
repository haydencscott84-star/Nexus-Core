
TARGET_FILE = "/root/nexus_spreads.py"

CLEAN_POPULATE_CHAIN = """    def populate_chain(self, data, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.", "WIN %")
            
            cur_price = getattr(self, "closed_price", 0.0)
            if cur_price <= 0: cur_price = 500.0
            
            if ivr > 50: prob_txt = "[bold green]Rich (High IV)[/]"
            elif ivr < 30: prob_txt = "[bold red]Low IV[/]"
            else: prob_txt = "Neutral"

            if not data: return

            for s in data:
                try:
                    credit = float(s.get("credit", 0))
                    width = float(s.get("width", 5))
                    # Filter Bad Data
                    if credit >= width or credit <= 0: continue
                except: continue

                max_risk = width - credit
                ret_pct = (credit / max_risk) * 100 if max_risk > 0 else 0
                
                short_strike = float(s.get("short", 0))
                long_strike = float(s.get("long", 0))
                
                # Determine Strategy Type & Breakeven
                is_put_credit = short_strike > long_strike
                
                if is_put_credit:
                    strat_type = 'bull'
                    be = short_strike - credit
                else:
                    strat_type = 'bear'
                    be = short_strike + credit
                
                # Win % Calculation
                win_val = 0.0
                try:
                    # Robust Key Generation
                    k_float = f"{s['expiry']}|{float(short_strike):.1f}"
                    k_int = f"{s['expiry']}|{int(short_strike)}"
                    
                    omap = getattr(self, "orats_map", {})
                    orats_dat = omap.get(k_float)
                    if not orats_dat:
                        orats_dat = omap.get(k_int)
                    
                    # Debug Log Logic (Silent unless file exists/empty)
                    if not orats_dat:
                        try:
                            import os
                            log_file = '/tmp/nexus_win_debug.log'
                            # Only write if file exists to avoid disk spam, or create if debugging requested
                            # For now, auto-create to help diagnosis
                            if not os.path.exists(log_file) or os.path.getsize(log_file) < 50000:
                                with open(log_file, 'a') as f:
                                     debug_keys = list(omap.keys())[:3] if omap else "EMPTY_MAP"
                                     f.write(f"MISS: Tried '{k_float}' / '{k_int}' | Map Size: {len(omap)} | Sample: {debug_keys}\\n")
                        except: pass
                    
                    if orats_dat:
                        iv = orats_dat.get('iv', 0.0)
                        win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                except:
                    pass

                if win_val == 0: win_str = "-"
                else: win_str = f"{win_val:.0f}%"

                row = [
                    s["expiry"], str(s["dte"]),
                    f"{short_strike:.1f}", f"{long_strike:.1f}",
                    f"${credit:.2f}",
                    f"${max_risk:.2f}",
                    f"[bold green]{ret_pct:.1f}%[/]" if ret_pct > 20 else f"{ret_pct:.1f}%",
                    prob_txt,
                    win_str
                ]
                
                key = f"{short_strike}|{long_strike}|{credit}|{short_strike}|{long_strike}|{width}"
                table.add_row(*row, key=key)
                
        except Exception as e:
            # self.log_msg(f"Chain Error: {e}")
            pass
"""

def apply_clean_overwrite():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        start_idx = -1
        end_idx = -1
        
        for i, line in enumerate(lines):
            if "def populate_chain(self, data, ivr=0.0):" in line:
                start_idx = i
            if start_idx != -1 and "@on(Input.Changed" in line:
                end_idx = i
                break
        
        if start_idx != -1 and end_idx != -1:
            print(f"Replacing lines {start_idx} to {end_idx} with CLEAN version...")
            new_lines = lines[:start_idx] + [CLEAN_POPULATE_CHAIN] + lines[end_idx:]
            
            with open(TARGET_FILE, 'w') as f:
                f.writelines(new_lines)
            print("Spread Chain Overwrite Complete.")
        else:
            print(f"Indices not found. Start: {start_idx}, End: {end_idx}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_clean_overwrite()
