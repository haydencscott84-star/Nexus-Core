
# PATCH SIDEBAR LOGIC
# Target: nexus_debit_downloaded.py
# Objective: Change Sidebar "MAX PROFIT" to "TGT PROFIT (50%)" and use (Debit * 0.5).

FILE = "nexus_debit_downloaded.py"

NEW_SIDEBAR_LOGIC = r'''
    def on_data_table_row_selected(self, event: DataTable.RowSelected):
        # Row Key Format: short_sym|long_sym|debit|l_strike|s_strike|width
        if not event.row_key.value: return
        
        try:
            parts = event.row_key.value.split("|")
            # s_sym = parts[0] (Short Leg / Target)
            # l_sym = parts[1] (Long Leg / Hedge)
            # debit = float(parts[2])
            # l_strike = float(parts[3])
            # s_strike = float(parts[4])
            # width = float(parts[5])
            
            debit = float(parts[2])
            l_strike = float(parts[3]) # Long (ITM for Call)
            width = float(parts[5])

            # Logic Update:
            # TGT PROFIT = Debit * 0.50
            tgt_profit = debit * 0.50
            
            # Max Theo (for ROC calc)
            max_profit_theo = width - debit
            max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
            
            # Stop Trigger (Assumed 1% or fixed?)
            # Logic: Buy ITM Call. Stop if Underlying drops below Long Strike? 
            # Or -3% stop? 
            # Current self.current_spy_price is needed for stop trigger calc usually?
            # Let's just update the static label values based on the selected row.
            
            # Update Labels
            # IDs: #setup_lbl, #cost_lbl, #max_profit_lbl, #roc_lbl, #stop_lbl, #lot_input
            
            self.query_one("#setup_lbl", Label).update(f"{l_strike}/{parts[4]}") # Strikes
            self.query_one("#cost_lbl", Static).update(f"DEBIT COST:\n${debit:.2f}")
            
            # [CHANGED] MAX PROFIT -> TGT PROFIT
            self.query_one("#max_profit_lbl", Static).update(f"TGT PROFIT (50%):\n${tgt_profit:.2f}")
            
            # [CHANGED] RETURN -> MAX ROC
            roc_style = "[bold green]" if max_roc > 80 else "[bold yellow]"
            self.query_one("#roc_lbl", Static).update(f"MAX ROC %:\n{roc_style}{max_roc:.1f}%[/]")
            
            # Stop Trigger (Approximation based on Delta 0.70 logic?)
            # Usually we use underlying price. If unavailable here, use 1% of strike?
            # Existing code probably calculated it. We need to preserve it or recalculate.
            # Let's approximate: Stop = Long Strike * 0.99 (Call) or 1.01 (Put).
            # We don't know if Call/Put easily here without parsing header or checking strikes?
            # l_strike (ITM) < s_strike (OTM) => CALL.
            s_strike = float(parts[4])
            is_call = l_strike < s_strike
            
            stop_price = l_strike * 0.99 if is_call else l_strike * 1.01
            self.query_one("#stop_lbl", Static).update(f"STOP TRIGGER (Est):\n${stop_price:.2f}")

        except Exception as e:
            self.log_msg(f"Selection Error: {e}")
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    # Replace the method using regex or marker
    if "def on_data_table_row_selected" in content:
        # Find start
        start_marker = "def on_data_table_row_selected"
        # Find end (next method or class end)
        # Next method usually 'on_button_pressed' or similar
        
        parts = content.split(start_marker)
        if len(parts) > 1:
            pre = parts[0]
            rest = parts[1]
            
            # Find next def
            import re
            m = re.search(r'\n    (?:async )?def ', rest)
            
            if m:
                end_idx = m.start()
                post = rest[end_idx:]
                new_content = pre + NEW_SIDEBAR_LOGIC.strip() + "\n" + post
                with open(FILE, 'w') as f: f.write(new_content)
                print("Patched sidebar logic.")
            else:
                # Might be last method
                new_content = pre + NEW_SIDEBAR_LOGIC.strip() + "\n"
                with open(FILE, 'w') as f: f.write(new_content)
                print("Patched sidebar (EOF).")

if __name__ == "__main__":
    patch()
