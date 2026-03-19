
import re

# RECOVERY PATCH: SAFE RESTORE of populate_debit_chain
TARGET_FILE = "/root/nexus_debit.py"

def apply_safe_recovery():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # SAFE METHOD (NO DEBUG DUMP)
        clean_method = """    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            
            # Prob Adj Logic
            if ivr < 30: 
                prob_txt = "[bold green]Cheap (Low IV)[/]"
            elif ivr > 50:
                prob_txt = "[bold red]Expensive[/]"
            else:
                prob_txt = "Neutral"

            for s in chain_data:
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
                else: 
                    be = l_strike - debit
                 
                # Calc Dist % (Only if price valid)
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
                
                # Win % (Broad Net Logic)
                l_delta = 0.0
                try:
                    if 'greeks' in s: l_delta = float(s['greeks'].get('delta', 0))
                    elif 'delta' in s: l_delta = float(s['delta'])
                    elif 'long_leg' in s: l_delta = float(s['long_leg'].get('greeks',{}).get('delta',0))
                    elif 'long' in s and isinstance(s['long'], dict): l_delta = float(s['long'].get('delta', 0))
                except: pass
                
                win_val = abs(l_delta * 100)
                win_str = f"{win_val:.0f}%"

                row = [
                    s["expiry"], str(s["dte"]),
                    f"{l_strike:.0f} (L)", f"{s_strike:.0f} (S)",
                    f"${debit:.2f}",
                    dist_str,
                    prob_txt,
                    Text(f"{max_roc:.1f}%", style=roc_style),
                    f"{be:.2f}",
                    win_str
                ]
                 
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                table.add_row(*row, key=key)
                 
        except Exception as e:
            self.log_msg(f"Populate Error: {e}")
"""

        # Regex to find the method block.
        # Starts with `def populate_debit_chain`
        # Ends before `def on_data_table_row_selected`
        
        regex = r'(\s*)def populate_debit_chain.+?def on_data_table_row_selected'
        
        # We need to include the next function header in the replacement so we don't delete it
        # Or we use a lookahead?
        # Let's just capture up to the start of the next function.
        
        regex = r'(\s{4})def populate_debit_chain.+?(?=\s{4}def on_data_table_row_selected)'
        
        if re.search(regex, content, re.DOTALL):
            content = re.sub(regex, clean_method, content, count=1, flags=re.DOTALL)
            print("SUCCESS: SAFE Method Overwritten Cleanly.")
            
            with open(TARGET_FILE, 'w') as f:
                f.write(content)
        else:
             print("ERROR: Could not locate method block for overwrite.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_safe_recovery()
