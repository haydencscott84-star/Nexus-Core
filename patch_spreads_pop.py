
import math

TARGET_FILE = "/root/nexus_spreads.py"

# 1. Imports
IMPORT_BLOCK = "import math\nimport aiohttp"

# 2. Methods to Inject
# Identical to nexus_debit, but poll needs correct ticker arg if strict (using SPY hardcoded for now as standard)
POLL_FUNC = """    async def poll_orats_greeks(self):
        while True:
            try:
                url = "https://api.orats.io/datav2/live/strikes"
                params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, params=params, timeout=10) as r:
                        if r.status == 200:
                            data = (await r.json()).get('data', [])
                            temp_map = {}
                            for i in data:
                                try:
                                    k = f"{i['expirDate']}|{float(i['strike']):.1f}"
                                    d = float(i.get('delta', 0))
                                    v = float(i.get('impliedVolatility', i.get('iv', 0)))
                                    temp_map[k] = {'delta': d, 'iv': v}
                                except: pass
                            if temp_map:
                                self.orats_map = temp_map
            except Exception as e:
                 # self.log_msg(f"ORATS Poll Error: {e}")
                 pass
            await asyncio.sleep(60)"""

HELPER_FUNC = """    def calculate_true_win_rate(self, spot_price, breakeven_price, dte, iv_annualized, risk_free_rate=0.045):
        try:
            if dte <= 0:
                return 100.0 if spot_price > breakeven_price else 0.0
            t = dte / 365.0
            v = iv_annualized
            r = risk_free_rate
            if v == 0 or t == 0 or spot_price <= 0 or breakeven_price <= 0: return 0.0
            ln_sk = math.log(spot_price / breakeven_price)
            drift = (r - 0.5 * v**2) * t
            vol_term = v * math.sqrt(t)
            d2 = (ln_sk + drift) / vol_term
            cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
            return cdf * 100
        except: return 0.0"""

# 3. New Populate Logic
POPULATE_FUNC = """    def populate_chain(self, data, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            # Add WIN % Column
            table.add_columns("EXPIRY", "DTE", "SHORT", "LONG", "CREDIT", "MAX RISK", "RETURN %", "PROB. ADJ.", "WIN %")

            cur_price = getattr(self, "current_spy_price", 0.0)
            if cur_price <= 0: cur_price = 0.01

            if ivr > 50: prob_txt = "[bold green]Rich (High IV)[/]"
            elif ivr < 30: prob_txt = "[bold red]Low IV[/]"
            else: prob_txt = "Neutral"

            if not data: return

            for s in data:
                # [FIX] Filter Bad Data
                try:
                    credit = float(s.get("credit", 0))
                    width = float(s.get("width", 5)) # Default 5 if missing
                    # Sanity Check: You cannot receive more credit than the width of the spread
                    if credit >= width or credit <= 0: continue
                except: continue

                max_risk = width - credit
                ret_pct = (credit / max_risk) * 100 if max_risk > 0 else 0
                
                short_strike = float(s.get("short", 0))
                long_strike = float(s.get("long", 0))
                
                # Determine Type (Put vs Call)
                # If Short < Long -> Put Credit Spread (Bullish) || e.g. Sell 400P, Buy 395P
                # If Short > Long -> Call Credit Spread (Bearish) || e.g. Sell 410C, Buy 415C
                is_put_check = short_strike < long_strike 
                
                # Breakeven Calculation
                if is_put_check:
                    # Put Credit: BE = Short Strike - Credit
                    be = short_strike - credit
                else:
                    # Call Credit: BE = Short Strike + Credit
                    be = short_strike + credit
                
                # Win % Calculation (PoP)
                win_val = 0.0
                try:
                    # Get IV from ORATS Map (Short Strike is the sold risk)
                    k = f"{s['expiry']}|{short_strike:.1f}"
                    orats_dat = getattr(self, "orats_map", {}).get(k, {})
                    iv = orats_dat.get('iv', 0.0)
                    
                    # Base PoP = Probability(Spot > Breakeven)
                    pop = self.calculate_true_win_rate(cur_price, be, float(s['dte']), iv)
                    
                    if is_put_check:
                        # Bullish: We win if Spot > BE. So PoP is correct.
                        win_val = pop
                    else:
                        # Bearish: We win if Spot < BE. So Win% = 100 - PoP.
                        win_val = 100.0 - pop
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
                
                # Key: Short|Long|Credit|ShortStrike|LongStrike|Width
                key = f"{short_strike}|{long_strike}|{credit}|{short_strike}|{long_strike}|{width}"
                table.add_row(*row, key=key)
                
        except Exception as e:
            # self.log_msg(f"Populate Error: {e}")
            pass"""

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()
            
        # 1. Inject Imports
        if "import math" not in content:
            content = content.replace("import asyncio", "import asyncio\nimport math\nimport aiohttp")
            print("Imports injected.")

        # 2. Inject Methods
        # Inject before populate_chain
        if "def calculate_true_win_rate" not in content:
            marker = "def populate_chain"
            if marker in content:
                content = content.replace(marker, f"{POLL_FUNC}\n\n{HELPER_FUNC}\n\n    {marker}")
                print("Helper functions injected.")
        
        # 3. Overwrite Populate Chain
        # Finding bounds for overwrite
        start_marker = "    def populate_chain(self, data, ivr=0.0):"
        start_idx = content.find(start_marker)
        if start_idx != -1:
            # Find next method or end
            # Assuming next method starts with '    def' or '    async def'
            # Or utilize the fact that usually populate is near end.
            # Let's search for next 'def ' at same indentation level (4 spaces)
            
            # Simple heuristic: Split lines, find start index, find next index with 4 space indent that starts definition
            lines = content.splitlines()
            s_lineno = -1
            e_lineno = -1
            
            for i, line in enumerate(lines):
                if line.rstrip() == start_marker.rstrip():
                    s_lineno = i
                elif s_lineno != -1 and i > s_lineno and (line.startswith("    def ") or line.startswith("    async def ")):
                    e_lineno = i
                    break
            
            if s_lineno != -1:
                if e_lineno == -1: e_lineno = len(lines)
                
                new_ns = lines[:s_lineno] + POPULATE_FUNC.splitlines() + lines[e_lineno:]
                content = "\n".join(new_ns)
                print("Populate logic updated.")
        
        # 4. Inject Poll Loop Start in on_mount
        # We need to make sure self.orats_map is init and loop started
        if "self.orats_map = {}" not in content:
            # Add to on_mount
            # Find on_mount
            if "def on_mount(self):" in content:
                content = content.replace("def on_mount(self):", "def on_mount(self):\n        self.orats_map = {}")
                print("on_mount map init injected.")
            
        if "self.run_worker(self.poll_orats_greeks)" not in content:
             if "self.run_worker(self.account_data_loop)" in content:
                 content = content.replace("self.run_worker(self.account_data_loop)", "self.run_worker(self.account_data_loop)\n        self.run_worker(self.poll_orats_greeks)")
                 print("Poll worker injected.")

        with open(TARGET_FILE, 'w') as f:
            f.write(content)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_patch()
