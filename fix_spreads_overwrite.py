
import math

TARGET_FILE = "/root/nexus_spreads.py"

# Clean Methods Block
CLEAN_BLOCK = """    def calculate_pop(self, spot, breakeven, dte, iv, strategy_type='bull'):
        try:
            # Handle Edge Cases
            if dte <= 0:
                if strategy_type == 'bull':
                    return 100.0 if spot > breakeven else 0.0
                else:
                    return 100.0 if spot < breakeven else 0.0
            
            # Constants
            t = dte / 365.0
            r = 0.045  # Risk-free rate approx 4.5%
            
            # Avoid div by zero
            if iv == 0 or t == 0 or spot <= 0 or breakeven <= 0: return 0.0

            # Black-Scholes d2 term
            ln_sk = math.log(spot / breakeven)
            drift = (r - 0.5 * iv**2) * t
            vol_term = iv * math.sqrt(t)
            
            d2 = (ln_sk + drift) / vol_term
            
            # Standard Normal CDF approximation
            cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
            
            if strategy_type == 'bull':
                return cdf * 100  # Prob Price > B/E
            else:
                return (1 - cdf) * 100  # Prob Price < B/E
        except: return 0.0

    def populate_chain(self, data, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.", "WIN %")

            cur_price = getattr(self, "current_spy_price", 0.0)
            if cur_price <= 0: cur_price = 0.01

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

def apply_overwrite():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Boundaries
        # Start: '    def calculate_pop'
        # End: '@on(Input.Changed, "#qty_input")'
        
        start_marker = "    def calculate_pop"
        end_marker = '@on(Input.Changed, "#qty_input")'
        
        s_idx = content.find(start_marker)
        e_idx = content.find(end_marker)
        
        if s_idx == -1:
            print("Error: Could not find start marker")
            # Fallback: maybe it's stuck on 'def calculate_true_win_rate'?
            # But the last patch successfully replaced it with calculate_pop name, just broke syntax.
            return
            
        if e_idx == -1:
             print("Error: Could not find end marker (on_qty_change)")
             # Fallback check - maybe it's just '    def on_qty_change'
             e_idx = content.find('    def on_qty_change')
        
        if e_idx == -1 or s_idx > e_idx:
            print("Error: Invalid boundaries")
            return

        # Replace Block
        old_block = content[s_idx:e_idx]
        new_content = content.replace(old_block, CLEAN_BLOCK)
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Overwrite Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_overwrite()
