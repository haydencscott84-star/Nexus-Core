
TARGET_FILE = "/root/nexus_spreads.py"

DEBUG_BLOCK = """    def populate_chain(self, data, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.", "WIN %")
            
            # DEBUG DUMP START
            try:
                import json
                with open('/tmp/spreads_debug_keys.txt', 'w') as f:
                    # Write first 5 chain items
                    sample_data = data[:2] if data else []
                    f.write(f"Chain Data Sample: {str(sample_data)}\\n")
                    
                    omap = getattr(self, "orats_map", {})
                    keys = list(omap.keys())[:5]
                    f.write(f"Orats Map Keys Sample: {str(keys)}\\n")
                    f.write(f"Total Orats Keys: {len(omap)}\\n")
            except Exception as e:
                # with open('/tmp/spreads_debug_err.txt', 'w') as f: f.write(str(e))
                pass
            # DEBUG DUMP END

            cur_price = getattr(self, "closed_price", 0.0)
            if cur_price <= 0: cur_price = 500.0
            
            if ivr > 50: prob_txt = "[bold green]Rich (High IV)[/]"
            elif ivr < 30: prob_txt = "[bold red]Low IV[/]"
            else: prob_txt = "Neutral"

            if not data: return

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

        # Find exact signature
        sig = "def populate_chain(self, data, ivr=0.0):"
        s_idx = content.find(sig)
        
        if s_idx == -1:
             print(f"Error: Signature '{sig}' not found")
             return

        # Find end
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
        
        # Check indentation of insertion point
        # s_idx points to 'def', likely preceeded by 4 spaces.
        # But we replace from s_idx.
        # DEBUG_BLOCK starts with '    def'.
        # If content has '    def', we should replace starting from '    def'.
        # find start of line
        line_start = content.rfind('\n', 0, s_idx) + 1
        
        # We replace from line_start to stop_idx?
        # That would include the indentation in old_block.
        
        old_block_full = content[line_start:stop_idx]
        
        # Check if old_block_full starts with newline, we typically want to preserve it or replace it clean.
        # simpler: just replace content[line_start:stop_idx] with '\n' + DEBUG_BLOCK
        
        new_content = content[:line_start] + "\n" + DEBUG_BLOCK + content[stop_idx:]
        
        # Remove potential double newline at start if present
        # actually DEBUG_BLOCK doesn't start with newline
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Debug Injection V3 Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inject_debug()
