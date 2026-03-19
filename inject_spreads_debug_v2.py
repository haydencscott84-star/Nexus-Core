
TARGET_FILE = "/root/nexus_spreads.py"

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
                    f.write(f"Chain Data Sample (First 2): {data[:2]}\\n")
                    omap = getattr(self, "orats_map", {})
                    keys = list(omap.keys())[:5]
                    f.write(f"Orats Map Keys Sample: {keys}\\n")
                    f.write(f"Total Orats Keys: {len(omap)}\\n")
            except: pass
            # DEBUG DUMP END

            cur_price = getattr(self, "closed_price", 0.0) 
            if cur_price == 0: cur_price = 500.0 
            
            ivr = getattr(self, "ivr", 0)
            if ivr < 30: prob_txt = "[bold green]Low IV[/]"
            elif ivr > 50: prob_txt = "[bold red]High IV[/]"
            else: prob_txt = "Neutral"

            for s in data:
                try:
                    credit = float(s.get("credit", 0))
                    width = float(s.get("width", 5))
                    if credit >= width or credit <= 0: continue
                except: continue

                max_risk = width - credit
                ret_pct = (credit / max_risk) * 100 if max_risk > 0 else 0
                
                short_strike = float(s.get("short", 0))
                long_strike = float(s.get("long", 0))
                
                # Determine Strategy Type & Breakeven
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

        # Relaxed search
        s_idx = content.find("def populate_chain(self):")
        if s_idx == -1:
             print("Error: def populate_chain not found (relaxed)")
             return

        # Find end
        import re
        all_defs = [m.start() for m in re.finditer(r'\n    def ', content)]
        future_defs = [d for d in all_defs if d > s_idx]
        
        on_decs = [m.start() for m in re.finditer(r'\n    @on', content)]
        future_ons = [d for d in on_decs if d > s_idx] # Also check for Decorators
        
        candidates = sorted(future_defs + future_ons)
        if candidates:
            stop_idx = candidates[0]
        else:
            stop_idx = len(content)

        old_block = content[s_idx:stop_idx]
        
        # Check indentation of replace block
        # The DEBUG_BLOCK assumes 4 space indentation.
        
        # We need to preserve the definition line indentation? 
        # Actually our `s_idx` finds `def ...`.
        # The previous line sets context.
        # But we are replacing from `def ...`.
        # So we should ensure `DEBUG_BLOCK` starts with matching indentation.
        # But `s_idx` might be `    def ...` or `def ...` (at 0).
        # We did `content.find("def populate_chain")`. The content prior could be spaces.
        
        # Let's find start of line.
        line_start = content.rfind('\n', 0, s_idx) + 1
        indent = content[line_start:s_idx]
        
        # If indent is 4 spaces, fine. If 8, we might need adjustments?
        # But assuming file uses 4 spaces.
        
        new_content = content[:s_idx] + DEBUG_BLOCK.lstrip() + "\n" + content[stop_idx:]
        # Note: DEBUG_BLOCK starts with 4 spaces. lstrip() removes them.
        # But wait, we want to replace `def ...` which likely has indentation.
        # Actually, let's just use `replace` on the exact string match if possible, or careful slicing.
        
        # safer to use original `old_block` replacement logic from previous attempts
        # just ensuring we find the block correctly.
        
        new_content = content.replace(old_block, DEBUG_BLOCK + "\n")

        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Debug Injection Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inject_debug()
