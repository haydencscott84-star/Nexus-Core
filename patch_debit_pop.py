
import math

TARGET_FILE = "/root/nexus_debit.py"

# 1. New Imports
IMPORT_BLOCK = "import math\nimport aiohttp"

# 2. New Poll Function (Fetches Delta AND IV)
NEW_POLL_FUNC = """    async def poll_orats_greeks(self):
        while True:
            try:
                url = "https://api.orats.io/datav2/live/strikes"
                params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, params=params, timeout=10) as r:
                        if r.status == 200:
                            data = (await r.json()).get('data', [])
                            # Map: Exp|Strike -> {'delta': val, 'iv': val}
                            temp_map = {}
                            for i in data:
                                try:
                                    # Exp: YYYY-MM-DD
                                    # Strike: float
                                    k = f"{i['expirDate']}|{float(i['strike']):.1f}"
                                    # Handle missing values safely
                                    d = float(i.get('delta', 0))
                                    # ORATS sends "impliedVolatility" or "iv". Checking documentation/common pattern.
                                    # If not found, default to 0.
                                    v = float(i.get('impliedVolatility', i.get('iv', 0)))
                                    temp_map[k] = {'delta': d, 'iv': v}
                                except: pass
                            if temp_map:
                                self.orats_map = temp_map
            except Exception as e:
                 self.log_msg(f"ORATS Poll Error: {e}")
            await asyncio.sleep(60)"""

# 3. New Helper Function (B-S Logic)
HELPER_FUNC = """    def calculate_true_win_rate(self, spot_price, breakeven_price, dte, iv_annualized, risk_free_rate=0.045):
        try:
            if dte <= 0:
                return 100.0 if spot_price > breakeven_price else 0.0
            
            # Constants
            t = dte / 365.0
            v = iv_annualized
            r = risk_free_rate
            
            # Prevent math errors
            if v == 0 or t == 0 or spot_price <= 0 or breakeven_price <= 0: return 0.0
            
            # Calculate d2 (Probability of expiring ITM)
            ln_sk = math.log(spot_price / breakeven_price)
            drift = (r - 0.5 * v**2) * t
            vol_term = v * math.sqrt(t)
            
            d2 = (ln_sk + drift) / vol_term
            
            # Approximate Normal CDF (Error Function method)
            cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
            
            return cdf * 100
        except:
            return 0.0"""

# 4. New Populate Function
NEW_POPULATE_FUNC = """    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            
            # Prob Adj Logic
            if ivr < 30: 
                prob_txt = "[bold green]Cheap (Low IV)[/]"
            elif ivr > 50:
                prob_txt = "[bold red]Expensive[/]"
            else:
                prob_txt = "Neutral"

            for s in chain_data:
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
                else: 
                    be = l_strike - debit
                
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
                    # 1. Get ORATS Data
                    key = f"{s['expiry']}|{l_strike:.1f}"
                    orats_data = self.orats_map.get(key, {})
                    
                    # Support legacy check if map structure somehow mixed (safety)
                    if isinstance(orats_data, float): orats_data = {'delta': orats_data, 'iv': 0.0}
                    
                    l_iv = orats_data.get('iv', 0.0)
                    
                    # 2. Calculate PoP
                    # Note: We need Spot Price, Breakeven, DTE, IV
                    win_pct = self.calculate_true_win_rate(cur_price, be, float(s['dte']), l_iv)
                    
                except: pass
                
                # Fallback to Delta if PoP fails/returns 0 (e.g. no IV data)
                if win_pct == 0:
                     try:
                         # Try delta proxy
                         l_delta = orats_data.get('delta', 0.0)
                         if not is_call: l_delta = abs(l_delta - 1) # Put parity approx
                         win_pct = abs(l_delta * 100)
                     except: pass

                win_str = f"{win_pct:.0f}%"

                row = [
                    s["expiry"], str(s["dte"]),
                    f"{l_strike:.0f} (L)", f"{s_strike:.0f} (S)",
                    f"${debit:.2f}",
                    dist_str,
                    prob_txt,
                    Text(f"{max_roc:.1f}%", style=roc_style),
                    f"{be:.2f}",
                    win_str
                ]
                
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                table.add_row(*row, key=key)
                
        except Exception as e:
            self.log_msg(f"Populate Error: {e}")"""

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # 1. Inject Import
        if "import math" not in content:
            content = content.replace("import aiohttp", IMPORT_BLOCK)
            print("Import injected.")

        # 2. Inject Helper (inside class)
        # We find a good place, e.g., before populate_debit_chain
        if "def calculate_true_win_rate" not in content:
            marker = "def populate_debit_chain"
            if marker in content:
                content = content.replace(marker, f"{HELPER_FUNC}\n\n    {marker}")
                print("Helper function injected.")
            else:
                print("Could not find insertion point for helper.")

        # 3. Replace Poll Function
        # We need to find the old one. It's multi-line.
        # Ideally, we used a known string or replace by regex.
        # Given indent sensitivity, let's try finding the start and assuming structure or using a marker.
        # The tool output showed: '    async def poll_orats_greeks(self):'
        # We can try to replace the whole block if we can identify it.
        # Alternatively, since we are using 'write_to_file' to create this python script, we can implement smart replacement logic here.
        
        # Simple replace strategy: Find start, find next method start, replace in between.
        start_marker = "    async def poll_orats_greeks(self):"
        end_marker = "    def" # Next method
        
        start_idx = content.find(start_marker)
        if start_idx != -1:
            # Find next method after this one
            next_idx = content.find(end_marker, start_idx + 10)
            if next_idx != -1:
                old_func = content[start_idx:next_idx]
                content = content.replace(old_func, NEW_POLL_FUNC + "\n\n")
                print("Poll function updated.")
            else:
                 print("Could not find end of poll function.")
        else:
             print("Could not find poll function start.")

        # 4. Replace Populate Function
        # Similar strategy
        start_marker_pop = "    def populate_debit_chain(self, chain_data"
        start_idx_pop = content.find(start_marker_pop)
        if start_idx_pop != -1:
            # Find next method or end of class.
            # Usually populate is near the end, maybe check indentation.
            # Let's count indentation.
            # Assuming it's indented by 4 spaces.
            
            # Since populate might be long, finding the *exact* end is tricky. 
            # However, I know the signature.
            # Let's verify if I can just match the method signature and replace until the next "def " at same level.
            
            # Actually, I have the FULL implementation of populate above.
            # I can just overwrite the whole file content if I am careful.
            # But that's risky.
            
            # Use Python's ast or regex?
            # Regex to match indented block is safer.
            import re
            # Regex to capture method def and its body (indented lines)
            # This is complex.
            
            # Fallback: Read the file, identify line numbers for start/end, replace slice.
            lines = content.splitlines()
            s_line = -1
            e_line = -1
            
            for i, line in enumerate(lines):
                if line.strip().startswith("def populate_debit_chain"):
                    s_line = i
                elif s_line != -1 and line.strip().startswith("def ") and i > s_line:
                    e_line = i
                    break
            
            if s_line != -1:
                if e_line == -1: e_line = len(lines) # End of file
                
                # Replace lines
                new_lines = lines[:s_line] + NEW_POPULATE_FUNC.splitlines() + lines[e_line:]
                content = "\n".join(new_lines)
                print("Populate function updated.")
            else:
                 print("Could not find populate logic lines.")

        with open(TARGET_FILE, 'w') as f:
            f.write(content)
            
    except Exception as e:
        print(f"Patch Error: {e}")

if __name__ == "__main__":
    apply_patch()
