
import math

TARGET_FILE = "/root/nexus_debit.py"

# New Standardized Methods
# Indentation: 4 spaces for methods, 8 for body.

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

    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            if cur_price <= 0: cur_price = 0.01
            
            # Prob Adj Logic
            if ivr < 30: prob_txt = "[bold green]Cheap (Low IV)[/]"
            elif ivr > 50: prob_txt = "[bold red]Expensive[/]"
            else: prob_txt = "Neutral"

            for s in chain_data:
                try:
                    ask_short = float(s.get("ask_short", 0))
                    bid_long = float(s.get("bid_long", 0))
                    
                    debit = ask_short - bid_long
                    if debit <= 0: debit = 0.01 
                    
                    width_val = abs(float(s["short"]) - float(s["long"]))
                    max_profit_theo = width_val - debit
                    max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
                    
                    l_strike = float(s["short"]) 
                    s_strike = float(s["long"])
                    
                    is_call = l_strike < s_strike
                    if is_call: 
                        be = l_strike + debit
                        strat_type = 'bull'
                    else: 
                        be = l_strike - debit
                        strat_type = 'bear'
                    
                    # Calc Dist %
                    if cur_price > 1.0:
                        if is_call:
                            dist_pct = ((be - cur_price) / cur_price) * 100
                        else:
                            dist_pct = ((cur_price - be) / cur_price) * 100
                            
                        if dist_pct <= 0: dist_style = "[bold green]"
                        elif dist_pct < 0.5: dist_style = "[bold yellow]"
                        else: dist_style = "[white]"
                        
                        dist_str = f"{dist_style}{dist_pct:.2f}%[/]"
                    else:
                        dist_str = "---"

                    roc_style = "bold green" if max_roc > 80 else "bold yellow"
                    
                    # Win % (PoP Logic)
                    win_pct = 0.0
                    try:
                        key = f"{s['expiry']}|{l_strike:.1f}"
                        orats_data = self.orats_map.get(key, {})
                        if isinstance(orats_data, float): orats_data = {'delta': orats_data, 'iv': 0.0}
                        
                        l_iv = orats_data.get('iv', 0.0)
                        
                        # NEW CALL
                        win_pct = self.calculate_pop(cur_price, be, float(s['dte']), l_iv, strat_type)
                    except: pass
                    
                    if win_pct == 0: win_str = "-"
                    else: win_str = f"{win_pct:.0f}%"

                    row = [
                        s["expiry"], str(s["dte"]),
                        f"{l_strike:.1f}", f"{s_strike:.1f}",
                        f"${debit:.2f}",
                        dist_str,
                        prob_txt,
                        f"[{roc_style}]{max_roc:.1f}%[/]",
                        f"${be:.2f}",
                        win_str
                    ]
                    
                    key = f"{l_strike}|{s_strike}|{debit}|{width}|{s['expiry']}"
                    table.add_row(*row, key=key)
                except: continue
                
        except Exception as e:
            # self.log_msg(f"Populate Error: {e}")
            pass
"""

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Boundaries
        # We want to replace `calculate_true_win_rate` and `populate_debit_chain`.
        # They are adjacent in the file (lines 636 and 663).
        
        start_marker = "    def calculate_true_win_rate"
        
        # We need to find end of populate_debit_chain.
        # Looking at previous dumps, what follows populate_debit_chain?
        # Usually `on_qty_change` or `calculate_risk` or `execute_trade`.
        # Let's search for the next `    def ` after start_marker.
        
        s_idx = content.find(start_marker)
        if s_idx == -1:
            print("Error: Could not find calculate_true_win_rate")
            return

        # Find the end.
        # We know `populate_debit_chain` is the method AFTER `calculate_true_win_rate`.
        # So we want to replace BOTH.
        # Effectively replacing from `start_marker` until the start of the *next* method.
        
        # Determine the next method.
        # Scanning from s_idx...
        # We expect:
        # 1. calculate_true_win_rate body
        # 2. populate_debit_chain definition
        # 3. populate_debit_chain body
        # 4. Next method (e.g. `def on_select` or `def execute`?)
        
        rest = content[s_idx + 50:] # Skip start
        import re
        # Find next indented def (4 spaces)
        # Note: we need to skip `def populate_debit_chain`.
        
        # Let's just Regex find all `    def `
        all_defs = [m.start() for m in re.finditer(r'\n    def ', content)]
        # Filter for those after s_idx
        future_defs = [d for d in all_defs if d > s_idx]
        
        # The first one should be `populate_debit_chain` (we replace this too).
        # The second one is where we stop.
        
        if len(future_defs) >= 2:
            stop_idx = future_defs[1] # The one after populate_debit_chain
        else:
            # Maybe end of file? or decorators?
            # Let's try to look for `@on` like in spreads.
            on_decs = [m.start() for m in re.finditer(r'\n    @on', content)]
            future_ons = [d for d in on_decs if d > s_idx]
            
            if future_ons:
                stop_idx = future_ons[0]
            else:
                # End of file?
                stop_idx = len(content)

        old_block = content[s_idx:stop_idx]
        
        # Double check we are replacing the right thing
        if "populate_debit_chain" not in old_block:
             print("Warning: targeted block does not seem to contain populate_debit_chain")
             # It might mean calculate_true_win_rate is separate?
             # But we saw line numbers 636 and 663. They are close.
             pass

        new_content = content.replace(old_block, CLEAN_BLOCK + "\n")
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
            print("Debit Standardization Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_patch()
