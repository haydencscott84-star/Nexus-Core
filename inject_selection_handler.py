
# Inject on_chain_selected handler into nexus_spreads.py
import os

target_file = "/root/nexus_spreads.py"
print(f"Injecting Handler into {target_file}...")

handler_code = """
    @on(DataTable.RowSelected, "#chain_table")
    def on_chain_selected(self, event: DataTable.RowSelected):
        try:
            row_key = event.row_key.value
            parts = row_key.split('|')
            if len(parts) < 6: return
            
            expiry = parts[0]
            short_strike = float(parts[1])
            long_strike = float(parts[2])
            credit = float(parts[3])
            width = float(parts[4])
            is_put = parts[5] == "True"
            
            stop_trigger = short_strike
            
            # Symbol Construction
            from datetime import datetime
            dt = datetime.strptime(expiry, "%Y-%m-%d")
            fmt_date = dt.strftime("%y%m%d")
            type_str = "P" if is_put else "C"
            
            def make_sym(strike):
                s_int = int(strike * 1000)
                return f"SPY{fmt_date}{type_str}{s_int:08d}"
                
            short_sym = make_sym(short_strike)
            long_sym = make_sym(long_strike)
            
            self.selected_spread = {
                "short_sym": short_sym,
                "long_sym": long_sym,
                "short_strike": short_strike,
                "long_strike": long_strike,
                "credit": credit,
                "stop_trigger": stop_trigger,
                "is_put": is_put
            }
            
            self.query_one("#lbl_stop").update(f"${stop_trigger:.2f}")
            self.calculate_risk()
            self.query_one("#execute_btn").disabled = False
            
        except Exception as e:
            self.log_msg(f"Selection Error: {e}")

"""

try:
    with open(target_file, 'r') as f:
        lines = f.readlines()
        
    new_lines = []
    injected = False
    
    # Locate a good insertion point. After populate_chain is safe.
    # Looking for 'def on_qty_change' as the next method usually
    
    for line in lines:
        if 'def on_qty_change' in line and not injected:
            print("Found insertion point before on_qty_change...")
            new_lines.append(handler_code)
            new_lines.append(line)
            injected = True
        else:
            new_lines.append(line)
            
    if injected:
        with open(target_file, 'w') as f:
            f.writelines(new_lines)
        print("Successfully injected handler.")
    else:
        print("ERROR: Could not find insertion point 'def on_qty_change'.")

except Exception as e:
    print(f"Injection Error: {e}")
