import re
import math

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Add get_net_greeks helper
    helper_code = """
    def get_net_greeks(self, quantity, raw_delta, raw_gamma):
        # User defined logic for Net Greeks
        # direction_multiplier = 1 if side.lower() == 'long' else -1
        
        qty_val = float(quantity)
        is_long = qty_val > 0
        direction_multiplier = 1 if is_long else -1
        
        multiplier = 100
        
        # Net Delta = raw * dir * abs(q) * 100
        net_delta = raw_delta * direction_multiplier * abs(qty_val) * multiplier
        
        # Net Gamma = raw * dir * abs(q) * 100
        net_gamma = raw_gamma * direction_multiplier * abs(qty_val) * multiplier
        
        return net_delta, net_gamma
"""
    
    # 2. Rewrite process_account_msg loop to populate pos_map correctly
    # We will basically replace the problematic loop structure.
    # The snippet had:
    # for p in raw_positions:
    #    if sym in processed_syms: continue
    
    # We want to change the logic so pos_map is filled regardless of processed_syms.
    # But Table addition respects processed_syms.
    
    # It's hard to regex replace a large block reliably.
    # Instead, we will modify the line `if sym in processed_syms: continue # Skip if part of spread`
    # We will remove the `continue` but wrap the TABLE ADDITION in the condition.
    # BUT wait, the loop does both pos_map and table add.
    
    # Strategy: 
    # Duplicate the loop? Or split it.
    # Easiest: Let the loop run for everything, populate pos_map for everything.
    # Only execute tbl.add_row if NOT in processed_syms.
    
    # Regex to find:
    # if sym in processed_syms: continue # Skip if part of spread
    
    # Replace with:
    # # if sym in processed_syms: continue # REMOVED for Data Integrity
    
    # Then wrap tbl.add_row with check?
    # Downstream: `tbl.add_row(...)`
    # verify where tbl.add_row is.
    
    # Let's be invasive and replace the whole block if possible, or use a smart patch.
    # The loop starts at `for p in raw_positions:`
    
    # Current Code:
    # for p in raw_positions:
    #    sym=p.get('Symbol')
    #    if sym in processed_syms: continue
    #    ... logic for nm, exp, etc ...
    #    self.pos_map[sym] = ...
    #    tbl.add_row(...)
    
    # Proposed Change:
    # for p in raw_positions:
    #    sym=p.get('Symbol')
    #    # if sym in processed_syms: continue <-- REMOVE
    #    ...
    #    self.pos_map[sym] = ...
    #    if sym not in processed_syms:
    #        tbl.add_row(...)
    
    if "if sym in processed_syms: continue" in content:
        print("Patching process_account_msg loop...")
        # 1. Remove the continue
        content = content.replace("if sym in processed_syms: continue", "# if sym in processed_syms: continue [PATCHED]")
        
        # 2. Wrap tbl.add_row
        # Find `tbl.add_row(` inside that loop... tricky with regex alone.
        # But we know the indentation.
        # tbl.add_row is likely indented 20 spaces (based on `for p` being 16).
        # We can add `if sym not in processed_syms:` before `tbl.add_row`.
        
        # However, `tbl.add_row` spans multiple lines.
        # It ends with `)` and usually `key=sym`.
        
        # Maybe easier to reconstruct the loop via replacement of the whole function segment?
        # The segment is identifiable.
        
        pass 
    else:
        print("Could not find exact loop line. Check source.")

    # Let's replace the loop logic entirely if we can identify start/end.
    # Identifying start: `for p in raw_positions:`
    # Identifying end: `if saved_cursor is not None ...`
    
    pattern_loop = r"(for p in raw_positions:)(.*?)(# RESTORE CURSOR)"
    
    # We need to write the new loop logic manually.
    new_loop = """for p in raw_positions:
                    sym=p.get('Symbol')
                    
                    q=int(p.get('Quantity',0)); 
                    if q==0: continue
                    nm, exp, typ, dte_val = parse_position_details(p)
                    mkt_val = _to_float(p.get('MarketValue', 0)); upnl = _to_float(p.get('UnrealizedProfitLoss', 0)); cost = _to_float(p.get('TotalCost', 0))
                    
                    # Sums only for displayed items? Or all? Usually Dashboard sums ALL.
                    # But if we sum Spreads (which sum legs) AND individual legs, we double count?
                    # The spreads code summing logic...
                    # Lines 850 said `# sum_val += g['raw_val']` was commented out.
                    # Use standard sum_val accumulation here for ALL legs to be sure.
                    sum_val += mkt_val; sum_pnl += upnl
                    
                    try: stk_val=float(re.search(r"(\\\\d+(?:\\\\.\\\\d+)?)", nm).group(1))
                    except: stk_val=0
                    
                    # --- STOPWATCH (AGE) ---
                    age_str = "?"
                    try:
                        ts_raw = p.get('Timestamp') or p.get('DateAcquired') or p.get('Created')
                        if ts_raw:
                            t_obj = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
                            now_obj = datetime.datetime.now(t_obj.tzinfo)
                            diff = now_obj - t_obj
                            days = diff.days; hours = diff.seconds // 3600; mins = (diff.seconds % 3600) // 60
                            if days > 0: age_str = f"{days}d {hours}h"
                            elif hours > 0: age_str = f"{hours}h {mins}m"
                            else: age_str = f"{mins}m"
                    except: age_str = "?"

                    stop="-"; t1="-"; t2="-"; t3="-"
                    if sym in self.oco: 
                        rule = self.oco[sym]
                        stop = f"${rule.get('stop', 0)}"
                        targets = rule.get('targets', [])
                        if targets and len(targets)>0: t1 = f"${targets[0]['price']}"
                        else: t1 = f"${rule.get('take', 0)}"

                    pct_pl = (upnl / cost * 100) if cost != 0 else 0.0
                    
                    raw_expiry = None
                    if p.get('ExpirationDate'):
                        try:
                            d_obj = datetime.datetime.fromisoformat(p['ExpirationDate'].replace('Z', '+00:00'))
                            raw_expiry = d_obj.strftime('%Y-%m-%d')
                        except: pass

                    # ALWAYS POPULATE MAP
                    self.pos_map[sym] = {
                        'sym':sym, 'desc':f"{nm} ({exp})", 'mkt':_to_float(p.get('Last',0)), 
                        'stk':stk_val, 'dte':dte_val, 'typ':typ, 'qty': q, 'pnl': pct_pl,
                        'mkt_val': mkt_val, 'cost': cost, 'AveragePrice': _to_float(p.get('AveragePrice', 0)),
                        'raw_expiry': raw_expiry,
                        'Delta': p.get('Delta', 0), 'Gamma': p.get('Gamma', 0),
                        'Theta': p.get('Theta', 0), 'Vega': p.get('Vega', 0),
                        'ImpliedVolatility': p.get('ImpliedVolatility', 0)
                    }
                    
                    # CONDITIONALLY ADD TO TABLE
                    if sym not in processed_syms:
                        tbl.add_row(Text(nm, style="green" if typ=="C" else "red"), exp, str(q), f"{mkt_val/eq*100:.1f}%", Text(f"{pct_pl:+.1f}%", style="green" if upnl>=0 else "red"), age_str, stop, t1, t2, t3, key=sym)
                
                # RESTORE CURSOR"""

    # Replace loop
    content = re.sub(pattern_loop, new_loop, content, flags=re.DOTALL)

    # 3. Replace calculate_net_delta logic
    print("Replacing calculate_net_delta...")
    new_calc = """
    def calculate_net_delta(self):
        \"\"\"Calculates Net Delta using cached ORATS Greeks + Live Price Adjustment + User Math.\"\"\"
        try:
            # Check if we have data
            if not hasattr(self, 'orats_chain') or self.orats_chain.empty:
                return 0.0

            if not self.pos_map: return 0.0

            net_delta = 0.0
            net_gamma = 0.0
            
            # Get Current Price
            try: curr_price = self.query_one(ExecutionPanel).und_price
            except: curr_price = 0
            
            if curr_price <= 0 and hasattr(self, 'fallback_price'): curr_price = self.fallback_price
            if curr_price <= 0: return 0.0

            df = self.orats_chain
            
            for sym, pos in self.pos_map.items():
                qty = float(pos.get('qty', 0))
                if qty == 0: continue
                
                # Parse Symbol
                try:
                    parts = sym.split() 
                    raw = parts[1]
                    y = "20" + raw[:2]; m = raw[2:4]; d = raw[4:6]
                    expiry = f"{y}-{m}-{d}"
                    typ_char = raw[6]
                    typ = "CALL" if typ_char == "C" else "PUT"
                    strike = float(raw[7:])
                    
                    # MATCH ORATS
                    mask = (df['expiry'] == expiry) & (df['type'] == typ) & (abs(df['strike'] - strike) < 0.01)
                    row = df[mask]
                    
                    if not row.empty:
                        r = row.iloc[0]
                        ref_delta = float(r['delta']) 
                        ref_gamma = float(r['gamma']) 
                        ref_price = float(r['stockPrice'] or curr_price)
                        
                        # Dynamic Adjust: New Delta ~= RefDelta + (Gamma * PriceDiff)
                        # But we should use the RECALCULATED delta for the User Formula?
                        # Or plug raw_delta into User Formula and let Gamma just be parallel?
                        # Typically "Current Delta" = Ref + (Gamma * Diff).
                        
                        curr_unit_delta = ref_delta + (ref_gamma * (curr_price - ref_price))
                        # Check bounds (-1 to 1)
                        # curr_unit_delta = max(-1.0, min(1.0, curr_unit_delta)) # Optional clamping
                        
                        # Apply User Math
                        # get_net_greeks(qty, raw_delta, raw_gamma)
                        # We pass the DYNAMIC delta as the "raw" input to the formula
                        d, g = self.get_net_greeks(qty, curr_unit_delta, ref_gamma)
                        
                        net_delta += d
                        net_gamma += g
                        
                    else:
                        # Fallback to TS Delta
                        pos_delta = float(pos.get('Delta', 0)) 
                        if pos_delta != 0:
                             # Approximate using same formula (Assuming TS delta is signed)
                             # TS Delta is already signed.
                             # If we use user formula, "raw" must be un-signed? 
                             # No, user formula expects signed inputs if logic holds.
                             # Let's just trust TS signed delta * 100 for fallback.
                             net_delta += (qty * pos_delta * 100) 
                except Exception as ex: 
                    pass 

            # Warn on Negative Gamma? (Optional)
            # if net_gamma < 0: self.log_msg(f"[WARN] Neg Gamma: {net_gamma:.1f}")

            return net_delta
        except Exception as e:
            return 0.0
"""
    # Helper injection
    if "def get_net_greeks" not in content:
        # Inject before calculate_net_delta
        content = content.replace("def calculate_net_delta", helper_code + "\n    def calculate_net_delta")
        
    # Replace method body
    content = re.sub(r"def calculate_net_delta\(self\):.*?(?=\s+def|\s+async def|\s+class|if __name__)", "", content, flags=re.DOTALL)
    # Re-insert new one (cleanup previous attempt if any)
    
    # We replaced the definition line too in the regex above? 
    # Yes "def calculate...".
    # So we just append the new code. Where?
    # Ideally where we removed it.
    
    # But string replacement removed it.
    # Let's just append it to class end? Or finding a marker.
    # The previous regex usage might be risky if multiple definitions exist (like my debug one).
    # I'll just append it to the end of the class (before main).
    
    if "if __name__ == " in content:
         content = content.replace("if __name__ == ", new_calc + "\nif __name__ == ")
    else:
         content += "\n" + new_calc

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
