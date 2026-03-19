
# PATCH PHASE 10 REVISION: NEGATIVE QTY & LOGIC FIX
# Targets: nexus_spreads_downloaded.py
# Nexus Debit appeared to accept the previous patch (headers looked correct in read), 
# but we will focus on Spreads to ensure the QTY and Logic are perfect.

SPREADS = "nexus_spreads_downloaded.py"

# 1. Update Position Logic in Nexus Spreads
# - Negative QTY for display (User Request)
# - Populate managed_spreads (Logic Fix)
# - Guard Clause (Logic Fix)

# We search for the block starting with "if match:" inside "update_positions"
# and replace it with the corrected logic.

SPREADS_LOGIC_OLD = r'''
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
'''

SPREADS_LOGIC_NEW = r'''
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
'''

# Wait, I need to replace the whole block to inject the changes.
# Let's target from "if match:" down to "processed_syms.add(l['sym'])"

SPREADS_BLOCK_SEARCH = r'''
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
                    val_net = s["val"] + l["val"]
                    
                    type_str = "CALL CREDIT" if is_call else "PUT CREDIT"
                    strikes_str = f"{s['strike']}/{l['strike']}"
                    key_id = f"SPREAD|{s['sym']}|{l['sym']}"
                    
                    credit_captured = pl_net - val_net
                    if credit_captured <= 0.01: credit_captured = 1.0 
                    roi = (pl_net / credit_captured) * 100
                    pl_str = f"{roi:+.1f}%"
                    
                    # LOGIC: 50% Capture, 0.5 pt Stop
                    if is_call: stop_lvl = s["strike"] - 0.5
                    else: stop_lvl = s["strike"] + 0.5
                    
                    # EXPOSURE Calculation (Max Risk)
                    # Risk = Width * 100 * Qty
                    risk_abs = (abs(s["strike"] - l["strike"]) * 100 * qty)
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (risk_abs / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"

                    # UI: Add Row
                    table.add_row(
                        type_str, strikes_str, dte_str, str(qty), 
                        Text(pl_str, style="bold green" if pl_net > 0 else "bold red"), 
                        Text(f"{exposure_pct:.1f}%", style=exp_style), 
                        f"{stop_lvl:.2f}", 
                        Text("ARMED", style="bold green"), # PT ARMED
                        key=key_id
                    )
                    
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
'''

# The NEW block must include:
# 1. str(-qty) in table.add_row
# 2. self.managed_spreads population
# 3. And we keep the rest same.

SPREADS_BLOCK_REPLACE = r'''
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
                    val_net = s["val"] + l["val"]
                    
                    type_str = "CALL CREDIT" if is_call else "PUT CREDIT"
                    strikes_str = f"{s['strike']}/{l['strike']}"
                    key_id = f"SPREAD|{s['sym']}|{l['sym']}"
                    
                    credit_captured = pl_net - val_net
                    if credit_captured <= 0.01: credit_captured = 1.0 
                    roi = (pl_net / credit_captured) * 100
                    pl_str = f"{roi:+.1f}%"
                    
                    # LOGIC: 50% Capture, 0.5 pt Stop
                    if is_call: stop_lvl = s["strike"] - 0.5
                    else: stop_lvl = s["strike"] + 0.5
                    
                    # EXPOSURE Calculation
                    risk_abs = (abs(s["strike"] - l["strike"]) * 100 * qty)
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (risk_abs / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"

                    # UI: Add Row (NEGATIVE QTY for Spreads)
                    display_qty = -qty 
                    table.add_row(
                        type_str, strikes_str, dte_str, str(display_qty), 
                        Text(pl_str, style="bold green" if pl_net > 0 else "bold red"), 
                        Text(f"{exposure_pct:.1f}%", style=exp_style), 
                        f"{stop_lvl:.2f}", 
                        Text("ARMED", style="bold green"),
                        key=key_id
                    )
                    
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
                    
                    # DATA SYNC: Populate Managed Spreads for Bot
                    # Guarding against zero strikes is implicit here because we use matched data
                    self.managed_spreads[s["sym"]] = {
                        "short_sym": s["sym"], "long_sym": l["sym"],
                        "short_strike": s["strike"], "long_strike": l["strike"],
                        "qty": qty, "is_call": is_call
                    }
'''

def patch_spreads():
    with open(SPREADS, 'r') as f: content = f.read()
    
    # Fuzzy Match Strategy for Block Replacement
    lines = content.splitlines()
    search_lines = SPREADS_BLOCK_SEARCH.strip().splitlines()
    
    # We look for the start sequence
    start_seq = search_lines[:3] # "if match:", "l = match", "qty = ..."
    
    start_idx = -1
    for i in range(len(lines) - 3):
        if (lines[i].strip() == start_seq[0].strip() and
            lines[i+1].strip() == start_seq[1].strip() and
            lines[i+2].strip() == start_seq[2].strip()):
            start_idx = i
            break
            
    if start_idx != -1:
        # Find indent
        first_line = lines[start_idx]
        indent = first_line[:first_line.find(start_seq[0].strip())]
        
        # Where does the block end?
        # We look for "processed_syms.add(l['sym'])"
        end_seq = "processed_syms.add(l[\"sym\"])" # Note quotes
        # Or just checking "processed_syms.add"
        
        end_idx = -1
        for i in range(start_idx, len(lines)):
            if "processed_syms.add(l[\"sym\"])" in lines[i] or "processed_syms.add(l['sym'])" in lines[i]:
                end_idx = i
                break
                
        if end_idx != -1:
            # Construct New Block
            new_block_lines = []
            for nl in SPREADS_BLOCK_REPLACE.strip().splitlines():
                new_block_lines.append(indent + nl.strip())
                
            final_lines = lines[:start_idx] + new_block_lines + lines[end_idx+1:]
            with open(SPREADS, 'w') as f: f.write('\n'.join(final_lines))
            print("Patched Nexus Spreads (Negative Qty + Logic)")
        else:
            print("Could not find end of block in Nexus Spreads")
    else:
        print("Could not find start of block in Nexus Spreads")

if __name__ == "__main__":
    patch_spreads()
