import os

import re

TARGET_FILE = "/root/nexus_debit.py"

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()
            
        # 1. ADD IMPORTS & CONSTANTS
        if "ORATS_API_KEY" not in content:
            imports = """import os
import aiohttp
import asyncio
import json
import time

ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
"""
            if "import sys" in content:
                content = content.replace("import sys", "import sys\n" + imports)
            else:
                content = imports + content
            print("Imports injected.")

        # 2. INJECT init_orats and poll_orats_greeks METHODS
        if "def poll_orats_greeks(self):" not in content:
            # Injecting map init
            if "self.orats_map = {}" not in content:
                content = content.replace("async def on_mount(self):", 
                                          "async def on_mount(self):\n        self.orats_map = {}\n        self.run_worker(self.poll_orats_greeks())")
                print("on_mount updated.")

            new_method = """
    async def poll_orats_greeks(self):
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
                                    temp_map[k] = float(i.get('delta', 0))
                                except: pass
                            if temp_map:
                                self.orats_map = temp_map
            except Exception as e:
                pass
            await asyncio.sleep(60)

"""
            if "def log_msg(self, msg):" in content:
                content = content.replace("def log_msg(self, msg):", new_method + "    def log_msg(self, msg):")
                print("poll_orats_greeks injected.")

        # 3. UPDATE populate_debit_chain specific logic
        # FIX V3: Force strict indentation by stripping previous line's spaces.
        
        # New code string starting with 4 spaces for definition
        new_populate_code = """    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            # [NEW] Added WIN % Column
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
                
                # Calc Dist % (Only if price valid)
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

                roc_style = "[bold green]" if max_roc > 80 else "[bold yellow]"
                
                # [NEW] WIN % CALCULATION via ORATS
                win_str = "-"
                try:
                    # Lookup Key: Exp|Strike
                    lookup_key = f"{s['expiry']}|{l_strike:.1f}"
                    c_delta = self.orats_map.get(lookup_key)
                    
                    if c_delta is not None:
                        if is_call:
                            final_delta = c_delta
                        else:
                            final_delta = c_delta - 1.0 # Put Delta logic
                        
                        win_val = abs(final_delta * 100)
                        win_str = f"{win_val:.0f}%"
                except Exception as ex:
                    pass

                row = [
                    s["expiry"], str(s["dte"]),
                    f"{l_strike:.0f} (L)", f"{s_strike:.0f} (S)",
                    f"${debit:.2f}",
                    dist_str,
                    prob_txt,
                    f"{roc_style}{max_roc:.1f}%[/]",
                    f"{be:.2f}",
                    win_str
                ]
                
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                table.add_row(*row, key=key)
                
        except Exception as e:
            self.log_msg(f"Populate Error: {e}")
"""

        start_marker_str = "def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):"
        end_marker_str = "def on_data_table_row_selected(self, event: DataTable.RowSelected):"

        start_idx = content.find(start_marker_str)
        end_idx = content.find(end_marker_str)

        if start_idx != -1 and end_idx != -1:
            # 1. Look backwards from start_idx to find the previous newline
            prev_newline = content.rfind('\n', 0, start_idx)
            if prev_newline == -1:
                # Should not happen as it's in a class
                print("Error: Could not find newline before function.")
                return
            
            # 2. Slice up to newline (exclusive of indent spaces)
            # content[:prev_newline+1] includes the \n.
            # Then we append our new code which starts with 4 spaces.
            
            new_content = content[:prev_newline+1] + new_populate_code + "\n    " + content[end_idx:]
            
            with open(TARGET_FILE, 'w') as f: f.write(new_content)
            print("populate_debit_chain Replaced Successfully (Strict Alignment).")
        else:
            print("Could not find method limits for replacement.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_patch()
