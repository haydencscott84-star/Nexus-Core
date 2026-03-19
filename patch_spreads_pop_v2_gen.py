
import math

TARGET_FILE = "/root/nexus_spreads.py"

# New Robust B-S Calculator with Strategy Type
POP_FUNC = """    def calculate_pop(self, spot, breakeven, dte, iv, strategy_type='bull'):
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
        except: return 0.0"""

# New Populate Logic with Correct Direction Detection
POPULATE_FUNC = """    def populate_chain(self, data, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            # Ensure WIN % is present
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
                # Put Credit Spread: Short Strike > Long Strike (e.g. Sell 400P, Buy 395P) -> Bullish
                # Call Credit Spread: Short Strike < Long Strike (e.g. Sell 410C, Buy 415C) -> Bearish
                
                is_put_credit = short_strike > long_strike
                
                if is_put_credit:
                    # Bullish: We want Price > Breakeven
                    strat_type = 'bull'
                    be = short_strike - credit
                else:
                    # Bearish: We want Price < Breakeven
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
            pass"""

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # 1. Update calculate_pop (or calculate_true_win_rate replacement)
        if "def calculate_pop" in content:
            # Logic to replace existing calculate_pop if it exists? 
            # Or just append/replace known block.
            pass 
        elif "def calculate_true_win_rate" in content:
            # Replace the old helper with the new one
            # Use marker logic similar to before, but we know the exact function signature
             marker = "def calculate_true_win_rate"
             end_marker = "def populate_chain" 
             # Rough replacement logic: find start of old func, replace until next func start
             s_idx = content.find(marker)
             e_idx = content.find(end_marker)
             if s_idx != -1 and e_idx != -1:
                 # Be careful not to delete populate_chain def line
                 old_block = content[s_idx:e_idx]
                 # We need to construct the new block with correct indentation
                 # The replacement POP_FUNC assumes 4 spaces
                 
                 # Actually, simpler: Removing the old function entirely
                 # then injecting the new one before populate_chain
                 # But regex replace is safer if we match exact signature line
                 pass

        # Strategy: 
        # 1. Remove `calculate_true_win_rate` if present.
        # 2. Inject `calculate_pop` before `populate_chain`.
        # 3. Overwrite `populate_chain`.
        
        lines = content.splitlines()
        new_lines = []
        skip = False
        
        # Rewrite file line by line
        for line in lines:
            # Skip old helper
            if "def calculate_true_win_rate" in line:
                skip = True
                continue
            if skip and "def populate_chain" in line:
                skip = False
                # While we are here, inject new helper BEFORE populate_chain
                new_lines.append(POP_FUNC + "\n\n")
            
            # Skip old populate_chain
            if "def populate_chain" in line:
                skip = True
                # Inject new populate chain
                new_lines.append(POPULATE_FUNC + "\n")
                continue
            
            # End of skip for populate_chain
            if skip:
                # Need to find end of function. 
                # Assuming next method or end of class detent
                # Just check indentation? Or assume it ends at next known method?
                # Nexus spreads has methods: on_mount, calculate_risk, execute_trade...
                # We can stop skipping when we see a line starting with 4 spaces that is NOT part of populate_chain
                # But populate_chain is likely big.
                # Use key markers: "def calculate_risk" or "def on_mount" etc?
                # Looking at cat output, populate_chain is followed by nothing? 
                # Wait, earlier cat output showed populate_chain at line 730 approx.
                # Let's look for known next markers.
                pass
                
                # Risky to rely on "next function".
                # Better to trust that if we see "    def " or "    async def " it's a new block
                if (line.strip().startswith("def ") or line.strip().startswith("async def ")) and line.startswith("    "):
                     skip = False
                     new_lines.append(line)
                continue
                
            new_lines.append(line)

        with open(TARGET_FILE, 'w') as f:
            f.write("\\n".join(new_lines))
            print("Patch Applied.")

    except Exception as e:
        print(f"Error: {e}")

# The above "rewrite" logic is fragile if I don't see the whole file. 
# Safer: Just overwrite the specific known text blocks via string replace
# I have the exact content of old definitions from the task boundary or memory?
# I know `calculate_true_win_rate` was injected.
# I know `populate_chain` starts with `def populate_chain(self, data, ivr=0.0):`

def apply_safe():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Define replacements
        
        # 1. Remove old calculate_true_win_rate if exists, and inject new POP_FUNC
        if "def calculate_true_win_rate" in content:
            # We assume it was injected right before populate_chain
            # We will use string searching to find the block
            s = content.find("def calculate_true_win_rate")
            e = content.find("def populate_chain")
            if s != -1 and e != -1 and s < e:
                # Replace the old helper with the new one
                old_helper = content[s:e]
                content = content.replace(old_helper, POP_FUNC + "\\n\\n")
                print("Replaced calculate_true_win_rate with calculate_pop")
            else:
                 # Fallback: Just inject new func if logic fails (risk of duplication but low impact)
                 print("Could not cleanly replace old helper. Injecting new one...")
                 content = content.replace("def populate_chain", POP_FUNC + "\\n\\n    def populate_chain")
        elif "def calculate_pop" not in content:
            # Inject it
             content = content.replace("def populate_chain", POP_FUNC + "\\n\\n    def populate_chain")
             print("Injected calculate_pop")

        # 2. Overwrite populate_chain
        # Use start marker and try to find end marker (next def class method or end of file)
        start_marker = "    def populate_chain(self, data, ivr=0.0):"
        if start_marker in content:
            s_idx = content.find(start_marker)
            # Find next method start indetented at level 1 (class method)
            # We assume standard 4 space indent for next method
            # We scan from s_idx + len(start_marker)
            rest = content[s_idx + len(start_marker):]
            # Find "\n    def " or "\n    async def "
            next_def = -1
            
            # Simple scan
            import re
            match = re.search(r'\\n    (async )?def ', rest)
            if match:
                next_def = match.start()
            
            if next_def != -1:
                # Replace content[s_idx : s_idx + len(start_marker) + next_def]
                end_idx = s_idx + len(start_marker) + next_def
                old_func = content[s_idx:end_idx]
                content = content.replace(old_func, POPULATE_FUNC) # POPULATE_FUNC includes replacement body but definition line? 
                # My POPULATE_FUNC string starts with "    def populate_chain..." which is perfect.
                print("Overwrote populate_chain (middle of file)")
            else:
                # Assume it's the last function
                old_func = content[s_idx:]
                content = content.replace(old_func, POPULATE_FUNC + "\\n")
                print("Overwrote populate_chain (end of file)")

        with open(TARGET_FILE, 'w') as f:
            f.write(content)
            print("Patch Applied Successfully.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_safe()

