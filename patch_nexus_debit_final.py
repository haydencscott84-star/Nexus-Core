
# PATCH NEXUS DEBIT FINAL: LOGIC & UI FIX
# Targets: nexus_debit_downloaded.py
# 1. Update Position Logic: Exposure %, ARMED, and Populate managed_spreads
# 2. Fix Auto Manager Loop: Use local data and Guard against Zero Strike

FILE = "nexus_debit_downloaded.py"

# --- REPLACEMENT BLOCKS ---

# 1. UPDATE POSITIONS (Complete Replacement to ensure integrity)
# We handle both Calls and Puts in one go or logic blocks.
# The original code has two blocks: Calls and Puts.
# We will inject the data sync and UI changes into both.

# Since replacing the entire method is risky with indentation, let's target the inner loop blocks.

# BLOCK A: CALL LOGIC
# Search for: "if k_short > k_long: # Bull Call"
# Replace from "if match:" down to "processed_syms.add(match.get('Symbol'))"

CALL_SEARCH = r'''
                    if match:
                        qty = l.get("Quantity")
                        pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                        val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                        cost = val - pl
                        if cost < 0.01: cost = 0.01 
                        roi = (pl / cost) * 100
                        pl_str = f"{roi:+.1f}%"

                        # LOGIC: 1% Stop, 1.5x Profit
                        stop_lvl = k_long * 0.99
                        profit_target = cost * 1.50
                        
                        strikes_str = f"{k_long}/{k_short}"
                        table.add_row("DEBIT CALL", strikes_str, dte_str, str(qty), pl_str, f"${val:.2f}", f"{stop_lvl:.2f}", f"${profit_target:.0f}")
                        processed_syms.add(l_sym)
                        processed_syms.add(match.get("Symbol"))
'''

CALL_REPLACE = r'''
                    if match:
                        qty = l.get("Quantity")
                        pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                        val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                        cost = val - pl
                        if cost < 0.01: cost = 0.01 
                        roi = (pl / cost) * 100
                        pl_str = f"{roi:+.1f}%"

                        # LOGIC: 1% Stop
                        stop_lvl = k_long * 0.99
                        
                        # EXPOSURE (Current Value / Equity)
                        equity = self.account_metrics.get("equity", 1)
                        exposure_pct = (val / equity * 100) if equity > 0 else 0
                        exp_style = "bold cyan" if exposure_pct > 5 else "cyan"

                        strikes_str = f"{k_long}/{k_short}"
                        table.add_row(
                            "DEBIT CALL", strikes_str, dte_str, str(qty), 
                            Text(pl_str, style="bold green" if pl > 0 else "bold red"), 
                            Text(f"{exposure_pct:.1f}%", style=exp_style),
                            f"{stop_lvl:.2f}", 
                            Text("ARMED", style="bold green")
                        )
                        processed_syms.add(l_sym)
                        processed_syms.add(match.get("Symbol"))
                        
                        # DATA SYNC
                        self.managed_spreads[l_sym] = {
                            "long_sym": l_sym, "short_sym": match.get("Symbol"),
                            "long_strike": k_long, "short_strike": k_short,
                            "qty": qty, "avg_price": cost, "is_call": True
                        }
'''

# BLOCK B: PUT LOGIC
# Search for: "if k_short < k_long:" -> "match = s" ... "if match:"
PUT_SEARCH = r'''
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    cost = val - pl
                    if cost < 0.01: cost = 0.01
                    roi = (pl / cost) * 100
                    pl_str = f"{roi:+.1f}%"
                    
                    stop_lvl = k_long * 1.01
                    profit_target = cost * 1.50
                    
                    strikes_str = f"{k_long}/{k_short}"
                    table.add_row("DEBIT PUT", strikes_str, dte_str, str(qty), pl_str, f"${val:.2f}", f"{stop_lvl:.2f}", f"${profit_target:.0f}")
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))
'''

PUT_REPLACE = r'''
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    cost = val - pl
                    if cost < 0.01: cost = 0.01
                    roi = (pl / cost) * 100
                    pl_str = f"{roi:+.1f}%"
                    
                    stop_lvl = k_long * 1.01
                    
                    # EXPOSURE
                    equity = self.account_metrics.get("equity", 1)
                    exposure_pct = (val / equity * 100) if equity > 0 else 0
                    exp_style = "bold cyan" if exposure_pct > 5 else "cyan"
                    
                    strikes_str = f"{k_long}/{k_short}"
                    table.add_row(
                        "DEBIT PUT", strikes_str, dte_str, str(qty), 
                        Text(pl_str, style="bold green" if pl > 0 else "bold red"), 
                        Text(f"{exposure_pct:.1f}%", style=exp_style),
                        f"{stop_lvl:.2f}", 
                        Text("ARMED", style="bold green")
                    )
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))
                    
                    # DATA SYNC
                    self.managed_spreads[l_sym] = {
                        "long_sym": l_sym, "short_sym": match.get("Symbol"),
                        "long_strike": k_long, "short_strike": k_short,
                        "qty": qty, "avg_price": cost, "is_call": False
                    }
'''

# 2. AUTO MANAGER LOOP (Guard against Zero Strike)
MGR_OLD = r'''
            for short_sym, spread in self.managed_spreads.items():
                if "long_sym" not in spread: continue
                
                long_strike = spread.get("long_strike", 0)
                entry_debit = abs(spread.get("avg_price", 0))
'''

MGR_NEW = r'''
            # Initial Clear if needed or rely on overwrite? 
            # We should probably clear stale ones? Or just let them be.
            # Ideally update_positions clears it.
            # Let's add the clearing at start of update_positions
            
            for key, spread in self.managed_spreads.items():
                # We key by long_sym now (in update_positions) or short_sym?
                # Nexus Debit original managed_spreads was keyed by short_sym? 
                # Original: self.managed_spreads = {s["short_sym"]: s ...}
                # My new code keys by l_sym: self.managed_spreads[l_sym] = ...
                # So we iterate items().
                
                long_strike = spread.get("long_strike", 0)
                if long_strike <= 0: continue # SAFETY GUARD
                
                entry_debit = abs(spread.get("avg_price", 0))
'''

# 3. CLEAR DICT IN UPDATE POSITIONS
# Old: processed_syms = set()
# New: processed_syms = set(); self.managed_spreads = {}

def replace_fuzzy(file_path, search_chunk, replace_chunk):
    with open(file_path, 'r') as f: content = f.read()
    
    lines = content.splitlines()
    search_lines = search_chunk.strip().splitlines()
    search_start = search_lines[0].strip()
    
    # 1. Find Start
    start_idx = -1
    for i, line in enumerate(lines):
        if search_start in line:
            # Verify a few more lines to be sure
            match = True
            for j in range(min(3, len(search_lines))):
                if i+j >= len(lines) or search_lines[j].strip() not in lines[i+j]:
                    match = False
                    break
            if match:
                start_idx = i
                break
    
    if start_idx == -1:
        print(f"Failed to find start block: {search_start}...")
        return

    # 2. Find End
    search_end = search_lines[-1].strip()
    end_idx = -1
    for i in range(start_idx, len(lines)):
        if search_end in lines[i]:
            end_idx = i
            break
            
    if end_idx == -1:
        print(f"Failed to find end block: {search_end}")
        return
        
    # 3. Replace
    # Detect Indent
    indent = lines[start_idx][:lines[start_idx].find(lines[start_idx].strip())]
    
    new_lines_list = []
    for nl in replace_chunk.strip().splitlines():
        new_lines_list.append(indent + nl.strip())
        
    final_lines = lines[:start_idx] + new_lines_list + lines[end_idx+1:]
    with open(file_path, 'w') as f: f.write('\n'.join(final_lines))
    print(f"Patched Block starting at line {start_idx}")

def patch():
    # 1. Calls
    replace_fuzzy(FILE, CALL_SEARCH, CALL_REPLACE)
    # 2. Puts
    replace_fuzzy(FILE, PUT_SEARCH, PUT_REPLACE)
    # 3. Manager Loop
    replace_fuzzy(FILE, MGR_OLD, MGR_NEW)
    # 4. Clear Dict
    with open(FILE, 'r') as f: c = f.read()
    c = c.replace('processed_syms = set()', 'processed_syms = set(); self.managed_spreads = {}')
    with open(FILE, 'w') as f: f.write(c)
    print("Patched Dictionary Init")

if __name__ == "__main__":
    patch()
