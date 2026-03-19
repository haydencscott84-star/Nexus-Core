
# PATCH P/L CALIBRATION
# Targets: nexus_spreads_downloaded.py
# Goal: Change P/L % from "Return on Risk" to "Percent of Max Profit Captured" (PL / Credit).

SPREADS_FILE = "nexus_spreads_downloaded.py"

NEW_SPREADS_UPDATE = r"""
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        import datetime
        
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
            # Get DTE
            expiry = key[:6]
            try:
                exp_dt = datetime.datetime.strptime(expiry, "%y%m%d")
                dte_val = (exp_dt - datetime.datetime.now()).days
                dte_str = f"{dte_val}d"
            except: dte_str = "-d"

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
                    
                    type_str = "CALL CREDIT" if is_call else "PUT CREDIT"
                    strikes_str = f"{s['strike']}/{l['strike']}"
                    key_id = f"SPREAD|{s['sym']}|{l['sym']}"
                    
                    # ---------------------------------------------------------
                    # [CALIBRATION] TRADE STATION MATCH (Percent Captured)
                    # ---------------------------------------------------------
                    # Credit = PL - Value (Since Value is negative for shorts)
                    # Example: PL=+200, Val=-800 => Credit (+1000) = 200 - (-800)
                    credit_captured = pl_net - val_net
                    
                    # Avoid Div/0
                    if credit_captured <= 0.01: credit_captured = 1.0 # Edge case
                    
                    # Percent Captured = PL / Credit
                    # This matches TS display for Credit Spreads
                    roi = (pl_net / credit_captured) * 100
                    
                    pl_str = f"{roi:+.1f}%"
                    
                    table.add_row(type_str, strikes_str, dte_str, str(qty), pl_str, f"${val_net:.2f}", key=key_id)
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
"""

def patch_file():
    with open(SPREADS_FILE, 'r') as f: content = f.read()
    
    start_marker = "def update_positions(self, positions):"
    end_marker = "async def fetch_managed_spreads_loop(self):"
    
    if start_marker in content:
        pre, post = content.split(start_marker, 1)
        if end_marker in post:
            body, remainder = post.split(end_marker, 1)
            final = pre + NEW_SPREADS_UPDATE.strip() + "\n    \n    " + end_marker + remainder
            with open(SPREADS_FILE, 'w') as f: f.write(final)
            print("Patched P/L Calculation for TradeStation Match.")
        else:
             # Try alternate end marker if method order shifted? 
             # Just look for indentation change usually, but marker is safer.
             # fallback to simple replacement if needed? No, let's trust previous structure.
             print("End marker not found")
    else:
        print("Start marker not found")

if __name__ == "__main__":
    patch_file()
