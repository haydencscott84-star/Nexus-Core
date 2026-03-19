
# PHASE 10 PATCH: UI POLISH (PT ARMED & EXPOSURE %)
# Targets: nexus_debit_downloaded.py, nexus_spreads_downloaded.py

DEBIT = "nexus_debit_downloaded.py"
SPREADS = "nexus_spreads_downloaded.py"

# --- 1. DEBIT: ON_MOUNT (Headers) ---
DEBIT_MOUNT_OLD = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "VALUE", "STOP (1%)", "PT (150%)")'
DEBIT_MOUNT_NEW = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")'

# --- 2. DEBIT: UPDATE_POSITIONS (Logic) ---
DEBIT_UPDATE_OLD = r'''
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

# --- 3. SPREADS: ON_MOUNT (Headers) ---
SPREADS_MOUNT_OLD = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "MKT VAL", "STOP (0.5pt)", "PT (50%)")'
SPREADS_MOUNT_NEW = 'pos_table.add_columns("STRATEGY", "STRIKES", "DTE", "QTY", "P/L OPEN", "EXPOSURE", "STOP", "PT")'

# --- 4. SPREADS: UPDATE_POSITIONS (Logic) ---
SPREADS_UPDATE_OLD = r'''
                    # Bot Logic Display
                    # Stop: Short Strike +/- 0.5
                    stop_level = 0.0
                    pt_level = 0.0
                    if is_call:
                        stop_level = short_strike - 0.5
                    else:
                        stop_level = short_strike + 0.5
                        
                    # PT = 50% Capture (Credit * 0.5)
                    # We don't have entry credit easily available here unless we track it.
                    # Estimate based on current? No.
                    # Just show "50%" for now or calculated if possible.
                    # Let's show "50% CAP" text.
                    pt_display = "50% CAP"

                    row = [
                        strat,
                        f"{short_strike}/{long_strike}",
                        str(dte)+"d",
                        str(qty),
                        Text(pl_str, style="bold green" if pl_net > 0 else "bold red"),
                        f"${val_net:.2f}",
                        f"{stop_level:.1f}",
                        pt_display
                    ]
'''

SPREADS_UPDATE_NEW = r'''
                    # Bot Logic Display
                    stop_level = 0.0
                    if is_call:
                        stop_level = short_strike - 0.5
                    else:
                        stop_level = short_strike + 0.5
                        
                    # Exposure
                    equity = self.account_metrics.get("equity", 1)
                    # For Credit Spreads, Exposure is usually Risk. But user asked for "Value" column replacement.
                    # Current columns: P/L OPEN, MKT VAL.
                    # MKT VAL for Credit Spread is cost to close (negative).
                    # Exposure probably means RISK (Margin Requirement)?
                    # Or just the % of equity consumed by this position (Margin)?
                    # Let's use Margin Requirement (Risk).
                    # Risk = Width * 100 * Qty - Credit? No, simply Width * 100 * Qty (Max Risk).
                    # Or maintenance margin. 
                    # "VALUE should represent the current exposure (%) in context to account value."
                    # For a spread, maximum loss is the exposure.
                    # Risk = (Width * 100 * Qty).
                    risk_abs = (abs(short_strike - long_strike) * 100 * qty)
                    exposure_pct = (risk_abs / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"

                    row = [
                        strat,
                        f"{short_strike}/{long_strike}",
                        str(dte)+"d",
                        str(qty),
                        Text(pl_str, style="bold green" if pl_net > 0 else "bold red"),
                        Text(f"{exposure_pct:.1f}%", style=exp_style), # EXPOSURE (Max Risk %)
                        f"{stop_level:.1f}",
                        Text("ARMED", style="bold green") # PT ARMED
                    ]
'''


def replace_chunk(file_path, old_chunk, new_chunk):
    with open(file_path, 'r') as f: content = f.read()
    
    # Check if exact match exists
    if old_chunk.strip() in content:
        # Simple replace (but careful with indentation for multi-line)
        # We need to preserve indentation of the block being replaced.
        # But replace() works on exact strings.
        # The multi-line chunks above are raw strings, but they might not capture the exact indentation in file.
        # Let's try splitting by unique markers inside the chunks if exact match fails.
        final = content.replace(old_chunk.strip(), new_chunk.strip())
        with open(file_path, 'w') as f: f.write(final)
        print(f"Patched: {file_path}")
        return

    # If exact match fails (likely due to whitespace), use flexible replacement
    print(f"Warning: Exact chunks not found in {file_path}. Trying fuzzy match...")
    
    # Try finding unique lines
    lines = content.splitlines()
    old_lines = old_chunk.strip().splitlines()
    first_line_clean = old_lines[0].strip()
    
    start_idx = -1
    for i, line in enumerate(lines):
        if first_line_clean in line:
            start_idx = i
            break
            
    if start_idx != -1:
        # Found start. Now find end.
        last_line_clean = old_lines[-1].strip()
        end_idx = -1
        for i in range(start_idx, len(lines)):
            if last_line_clean in lines[i]:
                end_idx = i
                break
        
        if end_idx != -1:
            # Replace lines start_idx to end_idx with new_chunk
            # Detect indentation of start_line
            indent = lines[start_idx][:lines[start_idx].find(first_line_clean)]
            
            new_lines_list = []
            for nl in new_chunk.strip().splitlines():
                new_lines_list.append(indent + nl.strip()) # Apply original indent
                
            final_lines = lines[:start_idx] + new_lines_list + lines[end_idx+1:]
            with open(file_path, 'w') as f: f.write('\n'.join(final_lines))
            print(f"Patched (Fuzzy): {file_path}")
        else:
            print(f"Could not find end line: {last_line_clean}")
    else:
        print(f"Could not find start line: {first_line_clean}")

if __name__ == "__main__":
    # DEBIT Headers
    replace_chunk(DEBIT, DEBIT_MOUNT_OLD, DEBIT_MOUNT_NEW)
    # DEBIT Logic
    replace_chunk(DEBIT, DEBIT_UPDATE_OLD, DEBIT_UPDATE_NEW)
    
    # SPREADS Headers
    replace_chunk(SPREADS, SPREADS_MOUNT_OLD, SPREADS_MOUNT_NEW)
    # SPREADS Logic
    replace_chunk(SPREADS, SPREADS_UPDATE_OLD, SPREADS_UPDATE_NEW)
