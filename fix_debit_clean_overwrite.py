
TARGET_FILE = "/root/nexus_debit.py"

CLEAN_METHOD = """    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            if cur_price <= 0: cur_price = 0.01
            
            # Prob Adj Logic
            if ivr < 30: prob_txt = "[bold green]Cheap (Low IV)[/]"
            elif ivr > 50: prob_txt = "[bold red]Expensive[/]"
            else: prob_txt = "Neutral"

            for s in chain_data:
                try:
                    ask_short = float(s.get("ask_short", 0))
                    bid_long = float(s.get("bid_long", 0))
                    
                    debit = ask_short - bid_long
                    if debit <= 0: debit = 0.01 
                    
                    width_val = abs(float(s["short"]) - float(s["long"]))
                    max_profit_theo = width_val - debit
                    max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
                    
                    l_strike = float(s["short"]) 
                    s_strike = float(s["long"])
                    
                    is_call = l_strike < s_strike
                    if is_call: 
                        be = l_strike + debit
                        strat_type = 'bull'
                    else: 
                        be = l_strike - debit
                        strat_type = 'bear'
                    
                    # Calc Dist %
                    if cur_price > 1.0:
                        if is_call:
                            dist_pct = ((be - cur_price) / cur_price) * 100
                        else:
                            dist_pct = ((cur_price - be) / cur_price) * 100
                            
                        if dist_pct <= 0: dist_style = "[bold green]"
                        elif dist_pct < 0.5: dist_style = "[bold yellow]"
                        else: dist_style = "[white]"
                        
                        dist_str = f"{dist_style}{dist_pct:.2f}%[/]"
                    else:
                        dist_str = "---"

                    roc_style = "bold green" if max_roc > 80 else "bold yellow"
                    
                    # Win % (PoP Logic)
                    win_pct = 0.0
                    try:
                        k_float = f"{s['expiry']}|{float(l_strike):.1f}"
                        k_int = f"{s['expiry']}|{int(l_strike)}"
                        
                        omap = getattr(self, "orats_map", {})
                        orats_data = omap.get(k_float)
                        if not orats_data:
                            orats_data = omap.get(k_int)
                        
                        # Debug Log Logic
                        if not orats_data:
                            try:
                                import os
                                log_file = '/tmp/debit_win_debug.log'
                                if not os.path.exists(log_file) or os.path.getsize(log_file) < 50000:
                                    with open(log_file, 'a') as f:
                                         debug_keys = list(omap.keys())[:3] if omap else "EMPTY_MAP"
                                         f.write(f"MISS: Tried '{k_float}' / '{k_int}' | Map Size: {len(omap)} | Sample: {debug_keys}\\n")
                            except: pass

                        if orats_data:
                            if isinstance(orats_data, float): orats_data = {'delta': orats_data, 'iv': 0.0}
                            iv = orats_data.get('iv', 0.0)
                            win_pct = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                    except: pass
                    
                    if win_pct == 0: win_str = "-"
                    else: win_str = f"{win_pct:.0f}%"

                    row = [
                        s["expiry"], str(s["dte"]),
                        f"{l_strike:.1f}", f"{s_strike:.1f}",
                        f"${debit:.2f}",
                        dist_str,
                        prob_txt,
                        f"[{roc_style}]{max_roc:.1f}%[/]",
                        f"${be:.2f}",
                        win_str
                    ]
                    
                    key = f"{l_strike}|{s_strike}|{debit}|{width_val}"
                    table.add_row(*row, key=key)
                except: continue

        except Exception as e:
            self.log_msg(f"Chain Error: {e}")
"""

def apply_clean_overwrite_debit():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        start_idx = -1
        end_idx = -1
        
        for i, line in enumerate(lines):
            if "def populate_debit_chain(self, chain_data" in line:
                start_idx = i
            if start_idx != -1 and "def on_qty_change" in line:
                end_idx = i - 1 # Just before the next decorator/method
                break
        
        # Determine strict end if not found
        if start_idx != -1 and end_idx == -1:
            # Look for @on(Input.Changed
            for i, line in enumerate(lines):
                if i > start_idx and "@on(Input.Changed" in line:
                     end_idx = i
                     break

        if start_idx != -1 and end_idx != -1:
            print(f"Replacing lines {start_idx} to {end_idx} with CLEAN version...")
            new_lines = lines[:start_idx] + [CLEAN_METHOD] + lines[end_idx:]
            
            with open(TARGET_FILE, 'w') as f:
                f.writelines(new_lines)
            print("Debit Chain Overwrite Complete.")
        else:
            print(f"Indices not found. Start: {start_idx}, End: {end_idx}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_clean_overwrite_debit()
