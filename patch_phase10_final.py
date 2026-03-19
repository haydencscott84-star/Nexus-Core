
# PATCH PHASE 10: UI POLISH + LOGIC FIX + ARCHITECTURE CLEANUP
# Targets: nexus_debit_downloaded.py, nexus_spreads_downloaded.py

DEBIT = "nexus_debit_downloaded.py"
SPREADS = "nexus_spreads_downloaded.py"

# ==============================================================================
# 1. DEBIT SNIPER (UI POLISH ONLY)
# ==============================================================================

# A. Headers
DEBIT_MOUNT_OLD = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "VALUE", "STOP (1%)", "PT (150%)")'
DEBIT_MOUNT_NEW = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")'

# B. Row Logic
DEBIT_UPDATE_OLD = '                        f"${pt_level:.2f}"\n                    ]'
DEBIT_UPDATE_OLD_FULL = r'''
                    # Stop/PT Logic (Visual)
                    stop_level = 0.0
                    pt_level = 0.0
                    if "C" in s['symbol']:
                        # Call: Stop 1% below Long Strike
                        stop_level = l_strike * (1 - DEFAULT_STOP_PCT)
                        pt_level = avg_price * 1.5
                    elif "P" in s['symbol']:
                        # Put: Stop 1% above Long Strike
                        stop_level = l_strike * (1 + DEFAULT_STOP_PCT)
                        pt_level = avg_price * 1.5
                        
                    row = [
                        "DEBIT " + ("CALL" if "C" in s["symbol"] else "PUT"),
                        f"{l_strike}/{s_strike}",
                        str(dte)+"d",
                        str(qty),
                        Text(pl_str, style="bold green" if pl > 0 else "bold red"),
                        f"${val:.2f}",
                        f"{stop_level:.2f}",
                        f"${pt_level:.2f}"
                    ]
'''

DEBIT_UPDATE_NEW = r'''
                    # Stop/PT Logic (Visual)
                    stop_level = 0.0
                    if "C" in s['symbol']:
                        stop_level = l_strike * (1 - DEFAULT_STOP_PCT)
                    elif "P" in s['symbol']:
                        stop_level = l_strike * (1 + DEFAULT_STOP_PCT)
                    
                    # Exposure Calc
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (val / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"
                        
                    row = [
                        "DEBIT " + ("CALL" if "C" in s["symbol"] else "PUT"),
                        f"{l_strike}/{s_strike}",
                        str(dte)+"d",
                        str(qty),
                        Text(pl_str, style="bold green" if pl > 0 else "bold red"),
                        Text(f"{exposure_pct:.1f}%", style=exp_style), # EXPOSURE
                        f"{stop_level:.2f}",
                        Text("ARMED", style="bold green") # PT ARMED
                    ]
'''

# ==============================================================================
# 2. CREDIT SPREADS (UI POLISH + LOGIC REFACTOR)
# ==============================================================================

# A. Headers
SPREADS_MOUNT_OLD = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "MKT VAL", "STOP (0.5pt)", "PT (50%)")'
SPREADS_MOUNT_NEW = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")'
# Also disable the flaky loop in on_mount
SPREADS_MOUNT_LOOP_OLD = 'self.run_worker(self.fetch_managed_spreads_loop)'
SPREADS_MOUNT_LOOP_NEW = '# self.run_worker(self.fetch_managed_spreads_loop) # DISABLED (Using update_positions)'


# B. Update Positions (Populate Managed Spreads + UI)
# We need to replace a large chunk of update_positions loop to inject the population logic
# AND change the UI row construction.

# Check current code structure via replace_block strategy?
# It's better to replace the core loop body.
# Target: "for s in shorts:" ... down to "table.add_row..."

# Let's create a partial replacement for the Inner Logic (Match Found)
SPREADS_LOGIC_OLD = r'''
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
                    initial_val = -credit_captured
                    target_val = initial_val * 0.50 
                    
                    if is_call: stop_lvl = s["strike"] - 0.5
                    else: stop_lvl = s["strike"] + 0.5
                    
                    table.add_row(type_str, strikes_str, dte_str, str(qty), pl_str, f"${val_net:.2f}", f"{stop_lvl:.2f}", f"${target_val:.0f}", key=key_id)
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
'''

SPREADS_LOGIC_NEW = r'''
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
                    
                    # DATA SYNC: Populate Managed Spreads for Bot
                    self.managed_spreads[s["sym"]] = {
                        "short_sym": s["sym"], "long_sym": l["sym"],
                        "short_strike": s["strike"], "long_strike": l["strike"],
                        "qty": qty, "is_call": is_call
                    }
'''

# Also need to clear managed_spreads at start of update_positions
# Old: "processed_syms = set()"
# New: "processed_syms = set(); self.managed_spreads = {}"

# C. Manager Loop Guard
MGR_LOOP_OLD = 'short_strike = spread.get("short_strike", 0)'
MGR_LOOP_NEW = 'short_strike = spread.get("short_strike", 0)\n                if short_strike <= 0: continue # Safety Guard'


def replace_chunk(file_path, old_chunk, new_chunk):
    with open(file_path, 'r') as f: content = f.read()
    
    # Try Exact
    if old_chunk.strip() in content:
        final = content.replace(old_chunk.strip(), new_chunk.strip())
        with open(file_path, 'w') as f: f.write(final)
        print(f"Patched: {file_path}")
        return

    # Try Fuzzy
    print(f"Warning: Exact match failed in {file_path}. Trying Fuzzy...")
    lines = content.splitlines()
    old_lines = old_chunk.strip().splitlines()
    first = old_lines[0].strip()
    
    # Debug: Print surrounding lines of potential match
    matches = [i for i, line in enumerate(lines) if first in line]
    if not matches:
        print(f"  Start line not found: '{first}'")
        return

    # Use first match
    start_idx = matches[0]
    
    # Find End
    last = old_lines[-1].strip()
    end_idx = -1
    for i in range(start_idx, len(lines)):
        if last in lines[i]:
            end_idx = i
            break
            
    if end_idx != -1:
        # Determine indentation
        orig_line = lines[start_idx]
        indent = orig_line[:orig_line.find(first)]
        
        new_lines_list = []
        for nl in new_chunk.strip().splitlines():
            new_lines_list.append(indent + nl.strip())
            
        final_lines = lines[:start_idx] + new_lines_list + lines[end_idx+1:]
        with open(file_path, 'w') as f: f.write('\n'.join(final_lines))
        print(f"Patched (Fuzzy): {file_path}")
    else:
        print(f"  End line not found: '{last}'")


if __name__ == "__main__":
    # DEBIT Headers
    replace_chunk(DEBIT, DEBIT_MOUNT_OLD, DEBIT_MOUNT_NEW)
    # DEBIT Row
    replace_chunk(DEBIT, DEBIT_UPDATE_OLD_FULL, DEBIT_UPDATE_NEW)
    
    # SPREADS Headers
    replace_chunk(SPREADS, SPREADS_MOUNT_OLD, SPREADS_MOUNT_NEW)
    # SPREADS Disable Loop
    replace_chunk(SPREADS, SPREADS_MOUNT_LOOP_OLD, SPREADS_MOUNT_LOOP_NEW)
    # SPREADS Row Logic + Populate
    replace_chunk(SPREADS, SPREADS_LOGIC_OLD, SPREADS_LOGIC_NEW)
    # SPREADS Manager Guard
    replace_chunk(SPREADS, MGR_LOOP_OLD, MGR_LOOP_NEW)
    
    # SPREADS Clear Dict
    replace_chunk(SPREADS, "processed_syms = set()", "processed_syms = set(); self.managed_spreads = {}")
