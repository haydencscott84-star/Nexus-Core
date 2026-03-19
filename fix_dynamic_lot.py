
import os

target_file = "/root/nexus_debit.py"
print(f"Applying Dynamic Lot Size Fix to {target_file}...")

# 1. New recalc_totals method (Updates correct labels)
# We need to update:
# - #lbl_debit (Total Cost)
# - #lbl_profit (Total Profit Target value)
# - #lbl_profit is "TGT PROFIT (50%)". If we buy 10, the profit $ amount is 50% of total cost.
# - The initial setup shows per-contract prices.
# Let's decide: Should right panel show PER CONTRACT or TOTAL?
# Usually, "DEBIT COST" implies total for the order. "LOT SIZE" is the multiplier.
# The user wants "dynamic", so they likely want to see the TOTAL needed.

new_recalc = """    def recalc_totals(self):
        if not self.selected_spread: return
        try:
            qty_val = self.query_one("#qty_input").value
            qty = int(qty_val) if qty_val and qty_val.isdigit() else 1
            
            debit_per = float(str(self.selected_spread.get("debit", 0)).replace("$", ""))
            total_cost = debit_per * qty * 100
            
            # Update DEBIT COST (Total)
            self.query_one("#lbl_debit").update(f"[bold yellow]${total_cost:.2f}[/]")
            
            # Update TGT PROFIT (Total Value at 50% gain)
            # Profit = 50% of Debit.
            # Total Value = Total Cost + Profit
            # OR just the Profit Amount? Label says "TGT PROFIT (50%)"
            # Previous logic was: (debit * 1.5). That represents the TARGET PRICE per contract.
            # If we show totals, we should show Target Value or Target Profit.
            # Let's stick to showing the TOTAL DEBIT (Cost) primarily.
            # But let's also update the Target Profit Amount if possible.
            
            profit_amt = (total_cost * 0.50)
            self.query_one("#lbl_profit").update(f"[bold green]${profit_amt:.2f} (50%)[/]")
            
        except Exception as e:
            self.log_msg(f"Recalc Error: {e}")
"""

# 2. Inject Handler for Input.Changed
handler_code = """
    @on(Input.Changed, "#qty_input")
    def on_qty_change(self, event: Input.Changed):
        self.recalc_totals()
"""

# Strategy:
# 1. Replace existing `recalc_totals` with new one.
# 2. Append handler code after `recalc_totals`.

with open(target_file, 'r') as f:
    content = f.read()

start_marker = "    def recalc_totals(self):"
end_marker = "    async def execute_trade(self):" # Next method

p1 = content.find(start_marker)
p2 = content.find(end_marker)

if p1 != -1 and p2 != -1:
    print(f"Replacing chunk from {p1} to {p2}...")
    # Construct replacement
    # We put the handler BEFORE execute_trade, right after recalc_totals
    replacement = new_recalc + "\n" + handler_code + "\n"
    
    new_content = content[:p1] + replacement + content[p2:]
    
    with open(target_file, 'w') as f:
        f.write(new_content)
    print("Success! Injected handler and updated logic.")
else:
    print("Could not locate method boundaries. Manual intervention required.")
