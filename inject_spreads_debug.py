
TARGET_FILE = "/root/nexus_spreads.py"

# We want to inject a debug print in populate_chain to see what keys it is building.
# We will use the robust overwrite method to update populate_chain temporarily.

# Existing populate_chain (approx):
# def populate_chain(self):
#     chain_data = ...
#     ...
#     k = f"{s['expiry']}|{short_strike:.1f}"

# We will create a patch that Logs 'k' vs keys in self.orats_map.
# Actually simpler: just dump one 's' and keys of orats_map to a file.

DEBUG_BLOCK = """    def populate_chain(self):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.", "WIN %")
            
            data = getattr(self, "chain_data", [])
            if not data: return

            # DEBUG DUMP START
            try:
                import json
                with open('/tmp/spreads_debug_keys.txt', 'w') as f:
                    # Write first 5 chain items
                    f.write(f"Chain Data Sample (First 2): {data[:2]}\\n")
                    # Write first 5 ORATS Map Keys
                    omap = getattr(self, "orats_map", {})
                    keys = list(omap.keys())[:5]
                    f.write(f"Orats Map Keys Sample: {keys}\\n")
                    f.write(f"Total Orats Keys: {len(omap)}\\n")
            except: pass
            # DEBUG DUMP END

            cur_price = getattr(self, "closed_price", 0.0) # Or current_spy_price
            # Fallback if 0
            if cur_price == 0: cur_price = 500.0 
            
            # Prob Adj Logic
            ivr = getattr(self, "ivr", 0)
            if ivr < 30: prob_txt = "[bold green]Low IV[/]"
            elif ivr > 50: prob_txt = "[bold red]High IV[/]"
            else: prob_txt = "Neutral"

            for s in data:
                try:
                    credit = float(s.get("credit", 0))
                    width = float(s.get("width", 5))
                    # Filter Bad Data
                    if credit >= width or credit <= 0: continue
                except: continue

                max_risk = width - credit
                ret_pct = (credit / max_risk) * 100 if max_risk > 0 else 0
                
                short_strike = float(s.get("short", 0))
                long_strike = float(s.get("long", 0))
                
                # Determine Strategy Type & Breakeven
                # Put Credit Spread: Short Strike > Long Strike (Bullish)
                is_put_credit = short_strike > long_strike
                
                if is_put_credit:
                    strat_type = 'bull'
                    be = short_strike - credit
                else:
                    strat_type = 'bear'
                    be = short_strike + credit
                
                # Win % Calculation
                win_val = 0.0
                try:
                    k = f"{s['expiry']}|{short_strike:.1f}"
                    orats_dat = getattr(self, "orats_map", {}).get(k, {})
                    iv = orats_dat.get('iv', 0.0)
                    
                    win_val = self.calculate_pop(cur_price, be, float(s['dte']), iv, strat_type)
                except: pass
                
                if win_val == 0: win_str = "-"
                else: win_str = f"{win_val:.0f}%"

                row = [
                    s["expiry"], str(s["dte"]),
                    f"{short_strike:.1f}", f"{long_strike:.1f}",
                    f"${credit:.2f}",
                    f"${max_risk:.2f}",
                    f"[bold green]{ret_pct:.1f}%[/]" if ret_pct > 20 else f"{ret_pct:.1f}%",
                    prob_txt,
                    win_str
                ]
                
                key = f"{short_strike}|{long_strike}|{credit}|{short_strike}|{long_strike}|{width}"
                table.add_row(*row, key=key)
                
        except Exception as e:
            pass
"""

def inject_debug():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Find populate_chain block
        start_marker = "    def populate_chain(self):"
        s_idx = content.find(start_marker)
        
        if s_idx == -1:
            print("Error: def populate_chain not found")
            return
            
        # Find end of populate_chain
        # Looking for next def or @on
        import re
        all_defs = [m.start() for m in re.finditer(r'\n    def ', content)]
        future_defs = [d for d in all_defs if d > s_idx]
        
        on_decs = [m.start() for m in re.finditer(r'\n    @on', content)]
        future_ons = [d for d in on_decs if d > s_idx]
        
        candidates = sorted(future_defs + future_ons)
        if candidates:
            stop_idx = candidates[0]
        else:
            stop_idx = len(content)

        old_block = content[s_idx:stop_idx]
        
        # Replace
        new_content = content.replace(old_block, DEBUG_BLOCK + "\n")
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Debug Injection Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inject_debug()
