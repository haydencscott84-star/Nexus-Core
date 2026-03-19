
# PATCH DEBIT FINAL UI
# Target: nexus_debit_downloaded.py
# 1. Change TGT PROFIT col to % TO B/E.
# 2. Format strikes as integers (no decimals).

FILE = "nexus_debit_downloaded.py"

NEW_POPULATE = r'''
    def populate_debit_chain(self, chain_data, width, target_strike=0.0):
        # NOTE: chain_data is now a LIST OF SPREADS from ts_nexus.py
        
        table = self.query_one("#chain_table", DataTable)
        table.clear(columns=True)
        # Headers: TGT PROFIT -> % TO B/E
        table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "B/E", "MAX ROC %")

        if not chain_data:
            self.log_msg("No spreads returned. Check Strike/Width.")
            return
            
        cur_price = self.current_spy_price
        if cur_price <= 0: cur_price = 0.01 # Avoid div by zero

        for s in chain_data:
            try:
                ask_short = float(s.get("ask_short", 0))
                bid_long = float(s.get("bid_long", 0))
                
                # Logic: Debit = Ask(Short) - Bid(Long)
                debit = ask_short - bid_long
                if debit <= 0: debit = 0.01 
                
                width_val = abs(float(s["short"]) - float(s["long"]))
                max_profit_theo = width_val - debit
                max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
                
                l_strike = float(s["short"]) 
                s_strike = float(s["long"])
                
                # Integer Formatting
                l_str = f"{l_strike:.0f}"
                s_str = f"{s_strike:.0f}"
                
                # Determine Type & B/E
                is_call = l_strike < s_strike
                if is_call: 
                    be = l_strike + debit
                    # % TO B/E (Distance needed to rise)
                    # (B/E - Spot) / Spot
                    dist_pct = ((be - cur_price) / cur_price) * 100
                else: 
                    be = l_strike - debit
                    # % TO B/E (Distance needed to fall)
                    # (Spot - B/E) / Spot
                    dist_pct = ((cur_price - be) / cur_price) * 100
                    
                # Style for Distance
                # If negative (already ITM past B/E), GREEN.
                # If positive (needs to move), YELLOW/RED if far.
                if dist_pct <= 0:
                    dist_style = "[bold green]"
                elif dist_pct < 0.5:
                    dist_style = "[bold yellow]"
                else:
                    dist_style = "[white]"
                    
                roc_style = "bold green" if max_roc > 80 else "bold yellow"
                
                row = [
                    s["expiry"], str(s["dte"]),
                    f"{l_str} (L)", f"{s_str} (S)",
                    f"${debit:.2f}", 
                    f"{dist_style}{dist_pct:.2f}%[/]", # % TO B/E
                    f"{be:.2f}",          
                    Text(f"{max_roc:.1f}%", style=roc_style)
                ]
                
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                table.add_row(*row, key=key)
                
            except Exception as e:
                self.log_msg(f"Error parsing spread row: {e}")

        self.log_msg(f"Showing {len(chain_data)} Debit Spreads.")
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    if "def populate_debit_chain" in content:
        import re
        pattern = r"(    def populate_debit_chain.*?)(?=\n    (?:async )?def |# END|\Z)"
        # Simple match might be safer than regex if regex fails on indent
        # Or just use the robust split method
        
    # Let's use the proven split method
    marker = "def populate_debit_chain(self, chain_data, width, target_strike=0.0):"
    parts = content.split(marker)
    if len(parts) > 1:
        pre = parts[0]
        # Find next method start in parts[1]
        next_def = re.search(r'\n    (?:async )?def ', parts[1])
        if next_def:
            end = next_def.start()
            post = parts[1][end:]
            new_content = pre + NEW_POPULATE.strip() + "\n" + post
            with open(FILE, 'w') as f: f.write(new_content)
            print("Replaced populate_debit_chain with Final Polish.")
        else:
            # Maybe EOF
            new_content = pre + NEW_POPULATE.strip() + "\n"
            with open(FILE, 'w') as f: f.write(new_content)
            print("Replaced populate_debit_chain (EOF).")
    else:
        print("Could not find method signature.")

if __name__ == "__main__":
    patch()
