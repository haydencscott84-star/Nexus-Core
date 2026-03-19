
# PATCH P/L PERCENTAGE DISPLAY
# Targets: nexus_debit.py (or downloaded) AND nexus_spreads.py (or downloaded)

DEBIT_FILE = "nexus_debit_downloaded.py"
SPREADS_FILE = "nexus_spreads_downloaded.py"

# --- DEBIT LOGIC ---
# Standard ROI: PL / (Val - PL)
DEBIT_LOGIC_NEW = r"""
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        # 1. GROUP POSITIONS BY EXPIRY
        import datetime
        expiry_groups = {}
        raw_map = {} 
        
        for p in positions:
            sym = p.get("Symbol", "")
            raw_map[sym] = p
            try:
                parts = sym.split(' ')
                if len(parts) > 1:
                    code = parts[1]
                    expiry = code[:6]
                    if expiry not in expiry_groups: expiry_groups[expiry] = []
                    expiry_groups[expiry].append(p)
            except: pass
            
        processed_syms = set()
        
        # Helper to get strike
        def get_k(s):
            import re
            m = re.search(r'[CP]([\d.]+)$', s)
            return float(m.group(1)) if m else 0

        for expiry, group in expiry_groups.items():
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
                    if k_short > k_long: # Bull Call
                        match = s
                        break
                
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    
                    # ROI Calc
                    cost = val - pl
                    if cost != 0:
                        roi = (pl / cost) * 100
                        pl_str = f"{roi:+.1f}%"
                    else:
                        pl_str = "0.0%"

                    stop_trig = "-"
                    if match.get("Symbol") in self.managed_spreads:
                        stop_trig = self.managed_spreads[match.get("Symbol")].get("stop_trigger", "-")
                        
                    table.add_row("DEBIT CALL", str(qty), pl_str, f"${val:.2f}", str(stop_trig))
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))

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
                    if k_short < k_long: # Bear Put
                        match = s
                        break
                        
                if match:
                    qty = l.get("Quantity")
                    pl = float(l.get("UnrealizedProfitLoss", 0)) + float(match.get("UnrealizedProfitLoss", 0))
                    val = float(l.get("MarketValue", 0)) + float(match.get("MarketValue", 0))
                    
                    cost = val - pl
                    if cost != 0:
                        roi = (pl / cost) * 100
                        pl_str = f"{roi:+.1f}%"
                    else:
                        pl_str = "0.0%"
                    
                    stop_trig = "-"
                    if match.get("Symbol") in self.managed_spreads:
                        stop_trig = self.managed_spreads[match.get("Symbol")].get("stop_trigger", "-")
                        
                    table.add_row("DEBIT PUT", str(qty), pl_str, f"${val:.2f}", str(stop_trig))
                    processed_syms.add(l_sym)
                    processed_syms.add(match.get("Symbol"))
"""

# --- SPREADS LOGIC ---
# Credit Spread ROI: PL / Risk
# Risk = (Width * 100 * Qty) - InitialCredit
# InitialCredit = PL - MarketValue
SPREADS_LOGIC_NEW = r"""
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        pos_map = {p.get("Symbol"): p for p in positions}
        processed_syms = set()
        
        def parse_sym(s):
            import re
            parts = s.split(' ')
            if len(parts) < 2: return None
            code = parts[1]
            m = re.match(r'^(\d{6})([CP])([\d.]+)$', code)
            if m:
                return {"expiry": m.group(1), "type": m.group(2), "strike": float(m.group(3)), "sym": s}
            return None

        groups = {}
        for sym, p in pos_map.items():
            meta = parse_sym(sym)
            if meta:
                key = f"{meta['expiry']}{meta['type']}"
                if key not in groups: groups[key] = []
                meta["qty"] = float(p.get("Quantity", 0))
                meta["pl"]  = float(p.get("UnrealizedProfitLoss", 0))
                meta["val"] = float(p.get("MarketValue", 0))
                groups[key].append(meta)

        for key, group in groups.items():
            is_call = "C" in key
            shorts = [x for x in group if x["qty"] < 0]
            longs  = [x for x in group if x["qty"] > 0]
            
            for s in shorts:
                if s["sym"] in processed_syms: continue
                match = None
                for l in longs:
                    if l["sym"] in processed_syms: continue
                    is_credit = False
                    if is_call:
                        if s["strike"] < l["strike"]: is_credit = True
                    else:
                        if s["strike"] > l["strike"]: is_credit = True
                    if is_credit:
                        match = l
                        break
                
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
                    val_net = s["val"] + l["val"]
                    type_str = "CALL" if is_call else "PUT"
                    label = f"{type_str} CREDIT ({s['strike']}/{l['strike']})"
                    key_id = f"SPREAD|{s['sym']}|{l['sym']}"
                    
                    # ROI Calc (Risk Basis)
                    # Risk = (Width * 100 * Qty) - Credit
                    # Credit = PL - Val
                    credit_captured = pl_net - val_net
                    width = abs(s["strike"] - l["strike"])
                    max_risk = (width * 100 * qty) - credit_captured
                    
                    # Safety
                    if max_risk <= 0: max_risk = 1.0 # Edge case?
                    
                    roi = (pl_net / max_risk) * 100
                    pl_str = f"{roi:+.1f}%"
                    
                    table.add_row(label, str(qty), pl_str, f"${val_net:.2f}", key=key_id)
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
"""

def replace_logic(file_path, start_marker, end_marker, new_content):
    try:
        with open(file_path, 'r') as f: content = f.read()
        if start_marker in content and end_marker in content:
            pre, post = content.split(start_marker, 1)
            body, remainder = post.split(end_marker, 1)
            final = pre + new_content.strip() + "\n    \n    " + end_marker + remainder
            with open(file_path, 'w') as f: f.write(final)
            print(f"Patched: {file_path}")
        else:
            print(f"Markers not found in {file_path}")
    except Exception as e:
        print(f"Error patching {file_path}: {e}")

if __name__ == "__main__":
    replace_logic(DEBIT_FILE, "def update_positions(self, positions):", "async def account_data_loop(self):", DEBIT_LOGIC_NEW)
    replace_logic(SPREADS_FILE, "def update_positions(self, positions):", "async def fetch_managed_spreads_loop(self):", SPREADS_LOGIC_NEW)
