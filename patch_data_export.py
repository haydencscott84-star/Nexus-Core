
import os

DASH_FILE = "trader_dashboard_v3.py"

# CONSTANTS FOR MATCHING
SECONDARY_PASS_START = "while shorts and longs:"
SECONDARY_PASS_APPEND = "grouped_display.append({"

# CODE TO INSERT IN SECONDARY PASS (Right after grouped_display.append block)
EXPORT_LOGIC = """                        
                        # Add to Data Export [FIXED]
                        grouped_data.append({
                            "type": "VERTICAL_SPREAD",
                            "short_leg": short_sym,
                            "long_leg": long_sym,
                            "qty": str(int(common_qty)),
                            "net_pl": pl_net,
                            "net_val": val_net,
                            "pl_pct": pl_pct,
                            "timestamp": ts_exp # Use expiry or something? Legged spreads have diff timestamps.
                        })
"""

# We need to find where to insert UNGROUPED POSITIONS export.
# It should be around line 893 where portfolio_snapshot is constructed.
SNAPSHOT_START = "portfolio_snapshot = {"
SNAPSHOT_END = "\"risk_profile\": {}"

# We need to build the ungrouped list first?
# Actually, the dashboard code iterates 'raw_positions' later (lines 808+) to add to table.
# But we construct snapshot BEFORE that? 
# In the file I viewed (Step 3698), snapshot construction (Line 883) is BEFORE table iteration (Line 808?? No wait).
# In Step 3698:
# Line 787: grouped_display, grouped_export = group_positions(...) (Actually line 787 says this)
# Line 790-806: Loop grouped
# Line 808-865: Loop individual (raw_positions)
# Line 871: Antigravity Dump section
# Line 883: Construct Snapshot
# So we can just collect ungrouped data.

# Better strategy:
# In `group_positions`, can we return ungrouped data too? 
# No, `group_positions` returns `processed_syms`.
# So we can construct the ungrouped list using `raw_positions` and `processed_syms` right before creating the snapshot.

UNGROUPED_LOGIC = """                
                # [FIX] Compile Ungrouped Positions for Export
                ungrouped_export = []
                for p in raw_positions:
                    sym = p.get('Symbol')
                    if sym in processed_syms: continue
                    q = int(p.get('Quantity', 0))
                    if q == 0: continue
                    
                    # Need to parse type/strike? Or just dump raw? 
                    # nexus_greeks expecting: ticker, qty, type, strike, expiry, raw
                    # But get_live_portfolio (Step 3790) parses raw 'ticker' (symbol).
                    # It just needs 'ticker' (symbol), 'qty', 'type'.
                    
                    ungrouped_export.append({
                        "ticker": sym,
                        "qty": q,
                        "type": p.get("AssetType", "OPTION"),
                        "raw": sym # nexus_greeks uses this
                    })
"""

SNAPSHOT_UPDATE = """                    "grouped_positions": grouped_export,
                    "ungrouped_positions": ungrouped_export, # [FIX] Add Ungrouped
"""

# Let's apply this via replace_file_content or a robust python re-writer.
# Since I need to insert code in multiple places, `replace_file_content` is safer than `sed` but maybe tedious.
# I will write a python script to read, modify, and write string.

def patch_file():
    with open(DASH_FILE, "r") as f:
        content = f.read()
    
    # 1. Fix Secondary Pass Export
    # Look for the grouped_display.append block in Secondary Pass.
    # Included a snippet of it to match.
    
    target_str = """                        grouped_display.append({
                            "label": label,
                            "exp": exp_str,
                            "qty": str(int(common_qty)),
                            "pl": pl_pct_str,
                            "val": f"${val_net:.2f}",
                            "key": f"AUTO|{short_sym}|{long_sym}",
                            "raw_pl": pl_net,
                            "raw_val": val_net,
                            "pl_pct": pl_pct,
                            "age": age_str
                        })"""
    
    replacement_str = target_str + """
                        
                        grouped_data.append({
                            "type": "VERTICAL_SPREAD",
                            "short_leg": short_sym,
                            "long_leg": long_sym,
                            "qty": str(int(common_qty)),
                            "net_pl": pl_net,
                            "net_val": val_net,
                            "pl_pct": pl_pct,
                            "timestamp": "" 
                        })"""
    
    # Identify specific occurrence. The Secondary Pass is the SECOND occurrence of grouped_display.append?
    # No, Primary Pass has one too.
    # Primary Pass has: "key": f"AUTO|{short_sym}|{long_sym}",
    # Secondary Pass has SAME key format?
    # Let's verify unique context.
    # Secondary Pass is inside `while shorts and longs:` loop.
    
    parts = content.split("while shorts and longs:")
    if len(parts) < 2:
        print("Error: Could not find Secondary Pass loop.")
        return
        
    pre_loop = parts[0]
    inside_loop = parts[1]
    
    # Now find grouped_display.append inside inside_loop
    if target_str in inside_loop:
        new_inside = inside_loop.replace(target_str, replacement_str, 1) # Only replace first occurrence in loop?
        content = pre_loop + "while shorts and longs:" + new_inside
        print("Fixed Secondary Pass Export.")
    else:
        print("Error: Could not find grouped_display.append in Secondary Pass.")
        # Debug: print snippet
        # print(inside_loop[:500])

    # 2. Add Ungrouped Compilation Logic
    # Insert before `portfolio_snapshot = {`
    
    snap_target = "portfolio_snapshot = {"
    if snap_target in content:
        content = content.replace(snap_target, UNGROUPED_LOGIC + "\n                " + snap_target)
        print("Added Ungrouped Data Compilation.")
    else:
        print("Error: Could not find portfolio_snapshot definition.")

    # 3. Add ungrouped_positions to snapshot dict
    # We want to replace `"grouped_positions": grouped_export,` with that + ungrouped.
    # Note: In lines 893 (Step 3694), it is `"grouped_positions": grouped_export, # [NEW] Export Spreads`
    
    dict_target = "\"grouped_positions\": grouped_export,"
    # Regex might be safer for spacing.
    import re
    
    # Simple replace might work if we are exact.
    # Try finding the line.
    match = re.search(r'("grouped_positions":\s*grouped_export.*)', content)
    if match:
        old_line = match.group(1)
        new_line = old_line + '\n                    "ungrouped_positions": ungrouped_export, # [FIX]'
        content = content.replace(old_line, new_line)
        print("Added ungrouped_positions key to snapshot.")
    else:
        print("Error: Could not find grouped_positions key in snapshot.")

    with open(DASH_FILE, "w") as f:
        f.write(content)
    print("Patch Complete.")

if __name__ == "__main__":
    patch_file()
