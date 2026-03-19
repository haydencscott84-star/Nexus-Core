
# PATCH LOT SCALING
# Target: nexus_debit_downloaded.py
# 1. Update on_data_table_row_selected to store unit values.
# 2. Add recalc_totals to handle Qty * 100 * Price logic.
# 3. Add on_qty_change listener.

FILE = "nexus_debit_downloaded.py"

NEW_BLOCK = r'''
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        # Filter for Chain Table only
        if event.data_table.id != "chain_table":
            return
            
        if not event.row_key.value: return
        
        try:
            parts = event.row_key.value.split("|")
            if len(parts) < 6: return
            
            # parts: [short_sym, long_sym, debit, l_strike, s_strike, width]
            debit = float(parts[2])
            l_strike = float(parts[3]) 
            s_strike = float(parts[4])
            width = float(parts[5])

            # STORE UNIT VALUES
            self.selected_unit_debit = debit
            self.selected_unit_width = width
            self.selected_strikes = f"{l_strike:.0f}/{s_strike:.0f}"
            
            # Set Setup Label safely
            try:
                self.query_one("#lbl_spread", Static).update(self.selected_strikes)
            except: pass

            # Update ROC (Rate of Return is constant %)
            max_profit_theo = width - debit
            max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
            roc_style = "[bold green]" if max_roc > 80 else "[bold yellow]"
            try:
                self.query_one("#lbl_roc", Static).update(f"{roc_style}{max_roc:.1f}%[/]")
            except: pass
            
            # Update Stop Trigger (Price Level is constant)
            try:
                is_call = l_strike < s_strike
                stop_price = l_strike * 0.99 if is_call else l_strike * 1.01
                self.query_one("#lbl_stop_trigger", Static).update(f"${stop_price:.2f}")
            except: pass

            # Enable Buttons
            try:
                self.query_one("#execute_btn", Button).disabled = False
            except: pass
            
            # RECALC TOTALS (Scales Cost/Profit)
            self.recalc_totals()

        except Exception as e:
            self.log_msg(f"Selection Error: {e}")

    def recalc_totals(self):
        """Updates Debit Cost and Target Profit based on Lot Size."""
        try:
            qty_val = self.query_one("#qty_input").value
            qty = int(qty_val) if qty_val and qty_val.strip() else 1
        except: 
            qty = 1
            
        unit_debit = getattr(self, "selected_unit_debit", 0.0)
        
        if unit_debit > 0:
            # Scale: Unit * Qty * 100 (Contract Multiplier)
            total_cost = unit_debit * qty * 100
            
            # Target is 50% of Debit
            total_target = (total_cost * 0.50)
            
            # Update Labels
            self.query_one("#lbl_debit", Static).update(f"${total_cost:,.2f}")
            self.query_one("#lbl_profit", Static).update(f"${total_target:,.2f}")

    @on(Input.Changed, "#qty_input")
    def on_qty_change(self, event):
        self.recalc_totals()
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    # We replace the existing on_data_table_row_selected AND append the new methods effectively
    # by replacing the block.
    # Logic: Regex find start of on_data_table_row_selected, find next method.
    # Replace that chunk with NEW_BLOCK.
    
    if "def on_data_table_row_selected" in content:
        import re
        # Pattern: Start of method -> Stop at next method start
        pattern = r"(    def on_data_table_row_selected.*?)(?=\n    (?:async )?def |# END|\Z)"
        
        match = re.search(pattern, content, re.DOTALL)
        if match:
            # We must be careful not to delete subsequent methods if they exist
            # checks if there are methods AFTER this one?
            # If on_data_table_row_selected is followed by other methods, we just replace it
            # and insert our new methods after it.
            # But wait, NEW_BLOCK contains 3 methods.
            # So we replace ONE method with THREE.
            
            old_code = match.group(1)
            new_code = NEW_BLOCK.strip()
            
            # Indentation handling: NEW_BLOCK has 4 spaces.
            # We replace directly.
            
            content = content.replace(old_code, "\n    " + new_code) 
            # Note: NEW_BLOCK starts with indentation in string? 
            # Yes, "    def...".
            # replace expectation: old_code has indentation.
            
            print("Injected Lot Scaling Logic (3 methods).")
            with open(FILE, 'w') as f: f.write(content)
        else:
            print("Regex fail on method block.")
    else:
        print("Method not found.")

if __name__ == "__main__":
    patch()
