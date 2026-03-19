
# PATCH NEXUS DEBIT V2: FULL METHOD REPLACEMENT
# Target: nexus_debit_downloaded.py
# Reason: Previous patch corrupted the logic blocks. We replace the entire update_positions method.

FILE = "nexus_debit_downloaded.py"

NEW_UPDATE_POSITIONS = r'''
    def update_positions(self, positions):
        # Phase 10 Logic: Exposure %, ARMED PT, Data Sync, Guarded Logic
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        # Reset Managed Spreads Sync
        self.managed_spreads = {}
        processed_syms = set()
        
        import datetime
        
        # 1. GROUP BY EXPIRY
        expiry_groups = {}
        for p in positions:
            sym = p.get("Symbol", "")
            try:
                parts = sym.split(' ')
                if len(parts) > 1:
                    code = parts[1]
                    expiry = code[:6]
                    if expiry not in expiry_groups: expiry_groups[expiry] = []
                    expiry_groups[expiry].append(p)
            except: pass
            
        def get_k(s):
            import re
            m = re.search(r'[CP]([\d.]+)$', s)
            return float(m.group(1)) if m else 0

        for expiry, group in expiry_groups.items():
            try:
                exp_dt = datetime.datetime.strptime(expiry, "%y%m%d")
                dte_val = (exp_dt - datetime.datetime.now()).days
                dte_str = f"{dte_val}d"
            except: dte_str = "-d"

            calls = [x for x in group if "C" in x.get("Symbol").split(' ')[1]]
            puts = [x for x in group if "P" in x.get("Symbol").split(' ')[1]]
            
            # --- CALLS ---
            long_calls = [c for c in calls if int(c.get("Quantity", 0)) > 0]
            short_calls = [c for c in calls if int(c.get("Quantity", 0)) < 0]
            
            for l in long_calls:
                l_sym = l.get("Symbol")
                if l_sym in processed_syms: continue
                k_long = get_k(l_sym)
                
                match = None
                for s in short_calls:
                    if s.get("Symbol") in processed_syms: continue
                    k_short = get_k(s.get("Symbol"))
                    if k_short > k_long: # Bull Call Spread
                        match = s
                        break
                
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

            # --- PUTS ---
            long_puts = [p for p in puts if int(p.get("Quantity", 0)) > 0]
            short_puts = [p for p in puts if int(p.get("Quantity", 0)) < 0]
            
            for l in long_puts:
                l_sym = l.get("Symbol")
                if l_sym in processed_syms: continue
                k_long = get_k(l_sym)
                
                match = None
                for s in short_puts:
                    if s.get("Symbol") in processed_syms: continue
                    k_short = get_k(s.get("Symbol"))
                    if k_short < k_long: # Bear Put Spread? No, Bull Put is Credit. Debit Put is Bearish.
                        # Debit Put: Long Strike > Short Strike? 
                        # Long Put (High Strike) + Short Put (Low Strike).
                        # e.g. Buy 100 Put, Sell 90 Put. k_long (100) > k_short (90).
                        pass
                    # Wait, logic check:
                    # Debit Put Spread: Long ITM/ATM, Short OTM.
                    # Usually Long Strike > Short Strike.
                    # e.g. Long 400P, Short 390P.
                    # Previous code: "if k_short < k_long:" 
                    if k_short < k_long:
                        match = s
                        break
                        
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

def patch_full_method():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    # Locate boundaries
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if "def update_positions(self, positions):" in line:
            start_idx = i
        
        # We find the NEXT method definition to define end
        if start_idx != -1 and i > start_idx:
            if "async def account_data_loop" in line or "def account_data_loop" in line:
                end_idx = i
                break
    
    if start_idx != -1 and end_idx != -1:
        # Construct new lines
        # Remove old method
        # Insert new method
        new_method_lines = [l + "\n" for l in NEW_UPDATE_POSITIONS.splitlines() if l.strip() != ""] 
        # Actually splitlines removes \n, so we add it back.
        
        # Ensure proper indentation? The string above has indentation.
        # But splitlines() yields lines.
        
        final_lines = lines[:start_idx] + [l + "\n" for l in NEW_UPDATE_POSITIONS.split("\n") if l] + lines[end_idx:]
        
        with open(FILE, 'w') as f: f.writelines(final_lines)
        print("Replaced update_positions method successfully.")
    else:
        print(f"Could not locate method boundaries. Start: {start_idx}, End: {end_idx}")

if __name__ == "__main__":
    patch_full_method()
