
# PATCH SIDEBAR FIXED V2
# Target: nexus_debit_downloaded.py
# 1. Correct IDs in Selection Logic (#lbl_spread, etc).
# 2. Update Layout Labels (MAX PROFIT -> TGT PROFIT).

FILE = "nexus_debit_downloaded.py"

# --- 1. NEW SELECTION LOGIC (Correct IDs) ---
NEW_SELECTION = r'''
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        # Filter for Chain Table only
        if event.data_table.id != "chain_table":
            return
            
        # Row Key Format: short_sym|long_sym|debit|l_strike|s_strike|width
        if not event.row_key.value: return
        
        try:
            parts = event.row_key.value.split("|")
            if len(parts) < 6: return
            
            debit = float(parts[2])
            l_strike = float(parts[3]) 
            s_strike = float(parts[4])
            width = float(parts[5])

            tgt_profit = debit * 0.50
            max_profit_theo = width - debit
            max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
            
            # Update Values (IDs from compose)
            # lbl_spread, lbl_debit, lbl_profit, lbl_roc, lbl_stop_trigger
            
            self.query_one("#lbl_spread", Static).update(f"{l_strike}/{s_strike}")
            self.query_one("#lbl_debit", Static).update(f"${debit:.2f}")
            self.query_one("#lbl_profit", Static).update(f"${tgt_profit:.2f}")
            
            roc_style = "[bold green]" if max_roc > 80 else "[bold yellow]"
            self.query_one("#lbl_roc", Static).update(f"{roc_style}{max_roc:.1f}%[/]")
            
            try:
                is_call = l_strike < s_strike
                stop_price = l_strike * 0.99 if is_call else l_strike * 1.01
                self.query_one("#lbl_stop_trigger", Static).update(f"${stop_price:.2f}")
            except:
                self.query_one("#lbl_stop_trigger", Static).update("-")
                
            # Enable Buttons?
            self.query_one("#execute_btn", Button).disabled = False

        except Exception as e:
            self.log_msg(f"Selection Error: {e}")
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    # --- 1. REPLACE SELECTION METHOD ---
    if "def on_data_table_row_selected" in content:
        import re
        pattern = r"(    def on_data_table_row_selected.*?)(?=\n    (?:async )?def |\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            content = content.replace(match.group(1), NEW_SELECTION.rstrip())
            print("Replaced selection logic with correct IDs.")
        else:
            print("Could not find selection logic block.")

    # --- 2. UPDATE STATIC LABELS IN COMPOSE ---
    # Label("MAX PROFIT:", classes="exec-label") -> Label("TGT PROFIT (50%):", classes="exec-label")
    if 'Label("MAX PROFIT:",' in content:
        content = content.replace('Label("MAX PROFIT:",', 'Label("TGT PROFIT (50%):",')
        print("Updated MAX PROFIT label.")
        
    if 'Label("RETURN (ROC):",' in content:
        content = content.replace('Label("RETURN (ROC):",', 'Label("MAX ROC %:",')
        print("Updated MAX ROC label.")

    with open(FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch()
