
TARGET_FILE = "/root/nexus_debit.py"

RECALC_METHOD = """    def recalc_totals(self):
        if not self.selected_spread: return
        try:
            qty_val = self.query_one("#qty_input").value
            qty = int(qty_val) if qty_val else 1
            
            debit = float(str(self.selected_spread.get("debit", 0)).replace("$", ""))
            total_cost = debit * qty * 100
            
            # self.query_one("#total_debit").update(f"${total_cost:.2f}")
        except: pass

"""

def add_recalc_method():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        # Check if already exists
        if any("def recalc_totals" in l for l in lines):
            print("Method already exists.")
            return

        # Insert after on_qty_change
        idx = -1
        for i, line in enumerate(lines):
            if "def on_qty_change" in line:
                idx = i + 2 # Skip def and body
                break
        
        if idx != -1:
            new_lines = lines[:idx] + [RECALC_METHOD] + lines[idx:]
            with open(TARGET_FILE, 'w') as f:
                f.writelines(new_lines)
            print("recalc_totals injected.")
        else:
            print("Could not find insertion point.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    add_recalc_method()
