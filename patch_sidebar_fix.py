
# PATCH SIDEBAR SELECTION FIX
# Target: nexus_debit_downloaded.py
# Objective: 1. Filter Check (Only update sidebar if #chain_table selected). 2. Enhanced Error Logging.

FILE = "nexus_debit_downloaded.py"

NEW_SELECTION = r'''
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        # Filter for Chain Table only
        if event.data_table.id != "chain_table":
            return
            
        # Row Key Format: short_sym|long_sym|debit|l_strike|s_strike|width
        if not event.row_key.value: return
        
        try:
            parts = event.row_key.value.split("|")
            
            if len(parts) < 6:
                self.log_msg(f"Invalid Key Format: {event.row_key.value}")
                return
            
            # s_sym = parts[0]
            # l_sym = parts[1]
            debit = float(parts[2])
            l_strike = float(parts[3]) 
            s_strike = float(parts[4])
            width = float(parts[5])

            tgt_profit = debit * 0.50
            max_profit_theo = width - debit
            max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
            
            # Update Labels
            self.query_one("#setup_lbl", Label).update(f"{l_strike}/{s_strike}")
            self.query_one("#cost_lbl", Static).update(f"DEBIT COST:\n${debit:.2f}")
            self.query_one("#max_profit_lbl", Static).update(f"TGT PROFIT (50%):\n${tgt_profit:.2f}")
            
            roc_style = "[bold green]" if max_roc > 80 else "[bold yellow]"
            self.query_one("#roc_lbl", Static).update(f"MAX ROC %:\n{roc_style}{max_roc:.1f}%[/]")
            
            try:
                is_call = l_strike < s_strike
                stop_price = l_strike * 0.99 if is_call else l_strike * 1.01
                self.query_one("#stop_lbl", Static).update(f"STOP TRIGGER (Est):\n${stop_price:.2f}")
            except:
                self.query_one("#stop_lbl", Static).update(f"STOP TRIGGER (Est):\n-")

        except Exception as e:
            self.log_msg(f"Selection Error: {e}")
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    # Replace method
    if "def on_data_table_row_selected" in content:
        import re
        # Regex to match the method signature and body until next method
        # We assume the indentation of next method is 4 spaces
        pattern = r"(    def on_data_table_row_selected.*?)(?=\n    (?:async )?def |\Z)"
        
        # Check if we can find it
        match = re.search(pattern, content, re.DOTALL)
        if match:
            old_block = match.group(1)
            new_block = NEW_SELECTION.rstrip() # remove trailing newline to avoid dupes if any
            content = content.replace(old_block, new_block)
            print("Replaced on_data_table_row_selected logic.")
        else:
            print("Could not match regex for selection method.")
            
    with open(FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch()
