
import re

# SAFE DEBUG PATCH V2
# Replaces populate_debit_chain with a version that dumps data to /tmp/nexus_debug_data.txt
TARGET_FILE = "/root/nexus_debit.py"

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # The METHOD with DEBUG instrumentation
        # Indentation must be correct (4 spaces inside class)
        new_method = """    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            # --- DEBUG DUMP V2 ---
            try:
                with open('/tmp/nexus_debug_data.txt', 'a') as df:
                    df.write("\\n--- EXECUTED ---\\n")
                    if chain_data and len(chain_data) > 0:
                        df.write(f"Sample Keys: {list(chain_data[0].keys())}\\n")
                        df.write(f"Sample Data: {chain_data[0]}\\n")
                    else:
                        df.write("Chain Data is Empty/None\\n")
            except Exception as e:
                pass
            # ---------------------

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
                
                # Win % (Placeholder until keys confirmed)
                l_delta = 0.0
                win_val = 0
                win_str = "0%"

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

        # REGEX: Capture the method signature up to "def on_data_table_row_selected"
        # We assume standard indentation (4 spaces)
        regex = r'(\s{4})def populate_debit_chain.+?(?=\s{4}def on_data_table_row_selected)'

        if re.search(regex, content, re.DOTALL):
            content = re.sub(regex, new_method, content, count=1, flags=re.DOTALL)
            
            with open(TARGET_FILE, 'w') as f:
                f.write(content)
            print("SUCCESS: Debug Method Injected.")
        else:
            print("ERROR: Regex match failed. Code structure might vary.")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_patch()
