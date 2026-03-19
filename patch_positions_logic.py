
DEBIT_FILE = "nexus_debit_downloaded.py"

NEW_LOGIC = r"""
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        # 1. GROUP POSITIONS BY EXPIRY
        # Map: Expiry -> [Pos1, Pos2, ...]
        import datetime
        expiry_groups = {}
        
        raw_map = {} # Key: Symbol, Val: PosData
        
        for p in positions:
            sym = p.get("Symbol", "")
            raw_map[sym] = p
            
            # Extract Expiry from Symbol (e.g., "SPY 251219C450")
            # Pattern: SPY YYMMDD[C/P]
            try:
                parts = sym.split(' ')
                if len(parts) > 1:
                    code = parts[1] # 251219C450
                    # Expiry is first 6 chars
                    expiry = code[:6]
                    if expiry not in expiry_groups: expiry_groups[expiry] = []
                    expiry_groups[expiry].append(p)
            except: pass
            
        # 2. IDENTIFY DEBIT SPREADS IN EACH GROUP
        # Debit Spread = Long Leg (Buy) + Short Leg (Sell)
        # Call Debit: Long Strike < Short Strike
        # Put Debit: Long Strike > Short Strike
        
        processed_syms = set()
        
        for expiry, group in expiry_groups.items():
            # Separate Calls and Puts
            calls = [x for x in group if "C" in x.get("Symbol").split(' ')[1]]
            puts = [x for x in group if "P" in x.get("Symbol").split(' ')[1]]
            
            # Helper to get strike
            def get_k(s):
                import re
                m = re.search(r'[CP]([\d.]+)$', s)
                return float(m.group(1)) if m else 0
                
            # Process Calls
            # Naive pairing: Match 1 Long with 1 Short
            long_calls = [c for c in calls if int(c.get("Quantity", 0)) > 0]
            short_calls = [c for c in calls if int(c.get("Quantity", 0)) < 0]
            
            for l in long_calls:
                l_sym = l.get("Symbol")
                if l_sym in processed_syms: continue
                
                # Find matching short (Credit < Debit usually, but strictly Strike < Short Strike for Debit Call)
                k_long = get_k(l_sym)
                
                # Find a short call with Strike > Long Strike (Debit Spread Definition)
                # And similar quantity magnitude
                match = None
                for s in short_calls:
                    if s.get("Symbol") in processed_syms: continue
                    k_short = get_k(s.get("Symbol"))
                    
                    if k_short > k_long: # Bull Call Spread (Debit)
                        match = s
                        break
                
                if match:
                    # FOUND A DEBIT SPREAD
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    
                    # Stop Trigger? Check managed_spreads
                    stop_trig = "-"
                    if match.get("Symbol") in self.managed_spreads:
                        stop_trig = self.managed_spreads[match.get("Symbol")].get("stop_trigger", "-")
                        
                    table.add_row("DEBIT CALL", str(qty), f"${pl:.2f}", f"${val:.2f}", str(stop_trig))
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))

            # Process Puts
            long_puts = [p for p in puts if int(p.get("Quantity", 0)) > 0]
            short_puts = [p for p in puts if int(p.get("Quantity", 0)) < 0]
            
            for l in long_puts:
                l_sym = l.get("Symbol")
                if l_sym in processed_syms: continue
                
                k_long = get_k(l_sym)
                
                # Find short put with Strike < Long Strike (Debit Put Spread / Bear Put)
                match = None
                for s in short_puts:
                    if s.get("Symbol") in processed_syms: continue
                    k_short = get_k(s.get("Symbol"))
                    
                    if k_short < k_long: # Bear Put Spread (Debit)
                        match = s
                        break
                        
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    
                    stop_trig = "-"
                    if match.get("Symbol") in self.managed_spreads:
                        stop_trig = self.managed_spreads[match.get("Symbol")].get("stop_trigger", "-")
                        
                    table.add_row("DEBIT PUT", str(qty), f"${pl:.2f}", f"${val:.2f}", str(stop_trig))
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))

"""

def apply_patch():
    with open(DEBIT_FILE, 'r') as f: content = f.read()
    
    # 1. REMOVE OLD update_positions method
    # It starts with 'def update_positions(self, positions):' and ends before 'async def account_data_loop'
    
    # Simple strategy: Identify the block and replace it.
    import re
    
    # Regex to match the method body is risky. 
    # Let's just find the start line and assumes it goes until 'async def account_data_loop'
    
    start_marker = "def update_positions(self, positions):"
    end_marker = "async def account_data_loop(self):"
    
    if start_marker in content and end_marker in content:
        # Construct the new content
        # We need to preserve indentation for the new method (4 spaces)
        
        # Split logic
        pre, post = content.split(start_marker, 1)
        # Inside 'post', find end_marker
        body, remainder = post.split(end_marker, 1)
        
        new_content = pre + NEW_LOGIC.strip() + "\n    \n    " + end_marker + remainder
        
        # Fix potential indentation issues in NEW_LOGIC (it's raw string, likely 0 indented, needs 4)
        # The NEW_LOGIC string above has 4 spaces already.
        
        with open(DEBIT_FILE, 'w') as f: f.write(new_content)
        print("Successfully patched update_positions logic.")
        
    else:
        print("Error: Could not locate method boundaries.")

if __name__ == "__main__":
    apply_patch()
