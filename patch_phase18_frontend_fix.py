
# PATCH PHASE 18 FRONTEND FIX
# Target: nexus_debit_downloaded.py
# Goal: 
# 1. Change IV Header Color to Yellow.
# 2. Use 'price' from reply to update current_spy_price.
# 3. Guard B/E Calculation against bad price.

FILE = "nexus_debit_downloaded.py"

NEW_FETCH_FIX = r'''
    @on(Button.Pressed, "#fetch_btn")
    async def on_fetch(self):
        self.run_worker(self.fetch_chain)

    async def fetch_chain(self):
        btn = self.query_one("#fetch_btn")
        btn.disabled = True
        btn.label = "SCANNING..."
        
        type_ = self.query_one("#type_select").value
        width_val = self.query_one("#width_input").value
        width = float(width_val) if width_val else 10.0
        
        strike_val = self.query_one("#strike_input").value
        target_strike = float(strike_val) if strike_val and strike_val.strip() else 0.0
        if target_strike <= 0:
            self.log_msg("⚠️ ERROR: Manual Strike Required for Debit Scan.")
            btn.disabled = False
            btn.label = "SCAN SETUP"
            return
            
        self.log_msg(f"Fetching Debit Setup: Strike {target_strike} Width {width}...")
        
        payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "strike": target_strike, "width": width}
        
        try:
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                # IV/IVR Logic
                iv = reply.get("iv", 0)
                ivr = reply.get("ivr", 0)
                price = reply.get("price", 0.0)
                
                # Update Internal Price
                if price > 0:
                    self.current_spy_price = price
                    try:
                        self.query_one("#spy_price_display", Static).update(f"SPY: {price:.2f}")
                    except: pass
                
                # Update Header - YELLOW for Visibility
                color = "white"
                if ivr < 30: color = "bold yellow" # CHANGED FROM GREEN
                elif ivr > 50: color = "bold red"
                
                iv_txt = f"[{color}]IV: {iv:.1f}% | IVR: {ivr:.0f}[/]"
                try: self.query_one("#lbl_iv_status", Label).update(iv_txt)
                except: pass
                
                if ivr > 50:
                    self.log_msg(f"⚠️ HIGH VOLATILITY (IVR {ivr}). DEBIT SPREADS EXPENSIVE.")
                
                self.populate_debit_chain(reply.get("data", []), width, target_strike, ivr)
            else:
                self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")
            
        btn.disabled = False
        btn.label = "SCAN SETUP"
'''

NEW_POPULATE_FIX = r'''
    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        try:
            table = self.query_one("#chain_table", DataTable)
            table.clear(columns=True)
            table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E")
            
            if not chain_data:
                self.log_msg("No spreads returned. Check Strike/Width.")
                return

            cur_price = getattr(self, "current_spy_price", 0.0)
            
            # Prob Adj Logic
            if ivr < 30: 
                prob_txt = "[bold green]Boost (+)[/]"
            elif ivr > 50:
                prob_txt = "[bold red]Drag (-)[/]"
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

                 roc_style = "bold green" if max_roc > 80 else "bold yellow"
                 
                 row = [
                     s["expiry"], str(s["dte"]),
                     f"{l_strike:.0f} (L)", f"{s_strike:.0f} (S)",
                     f"${debit:.2f}", 
                     dist_str,
                     prob_txt,
                     Text(f"{max_roc:.1f}%", style=roc_style),
                     f"{be:.2f}"
                 ]
                 
                 key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                 table.add_row(*row, key=key)
                 
        except Exception as e:
            self.log_msg(f"Populate Error: {e}")
'''

def patch_frontend_fix():
    with open(FILE, 'r') as f: content = f.read()
    
    # 1. Replace fetch_chain (logic update)
    import re
    # We look for the entire block including the decorator we just added?
    # Actually the wiring fix added the decorator but modified signatures.
    # The previous fetch_chain replace logic used regex.
    # Let's try to match the method body again.
    
    # Matches: async def fetch_chain ... to end of method
    pattern_fetch = r"(    async def fetch_chain.*?)(?=\n    (?:async )?def |# END|\Z)"
    match = re.search(pattern_fetch, content, re.DOTALL)
    if match:
        content = content.replace(match.group(1), NEW_FETCH_FIX.strip()) # NEW_FETCH_FIX includes on_fetch too, ensure we don't duplicate
        # Wait, NEW_FETCH_FIX has on_fetch AND fetch_chain.
        # If I replace just fetch_chain, I might duplicate or miss on_fetch.
        # The file currently has:
        # @on...
        # async def on_fetch...
        # async def fetch_chain...
        
        # Simplest: Replace both methods if they are adjacent.
        # Or replace individually.
        pass # Handle below
        
    # STRATEGY: 
    # Delete on_fetch and fetch_chain. Insert valid block.
    # Regex to find on_fetch AND fetch_chain
    # Pattern: @on.*?async def on_fetch.*?async def fetch_chain.*?btn.label = "SCAN SETUP"
    
    # Better: Just replace "async def fetch_chain" block with the NEW logic which does NOT include on_fetch in the string var (I must edit the string var).
    # Corrected NEW_FETCH_FIX to NOT include on_fetch, just fetch_chain, unless I want to ensure wiring.
    # The string above HAS on_fetch. 
    # I will replace the existing on_fetch AND fetch_chain with this block.
    
    # Regex: from "@on(Button.Pressed, \"#fetch_btn\")" down to end of fetch_chain.
    
    pattern_combo = r'(@on\(Button\.Pressed, "#fetch_btn"\).*?btn\.label = "SCAN SETUP")'
    match = re.search(pattern_combo, content, re.DOTALL)
    if match:
         content = content.replace(match.group(1), NEW_FETCH_FIX.strip())
         print("Replaced on_fetch + fetch_chain (Combo).")
    else:
        # Fallback: Maybe wiring didn't propagate exactly as expected (indentation?)
        print("Regex Combo failed. Trying method replacement.")
        # Just replace fetch_chain body
        p2 = r"(    async def fetch_chain.*?)(?=\n    (?:async )?def |# END|\Z)"
        m2 = re.search(p2, content, re.DOTALL)
        if m2:
             # Strip on_fetch from my NEW_FETCH_FIX variable for this fallback
             only_fetch = NEW_FETCH_FIX.split("async def fetch_chain(self):")[1]
             new_code = "    async def fetch_chain(self):" + only_fetch
             content = content.replace(m2.group(1), new_code)
             print("Replaced fetch_chain only.")
             
    # 2. Replace populate_debit_chain
    pattern_pop = r"(    def populate_debit_chain.*?)(?=\n    (?:async )?def |# END|\Z)"
    m3 = re.search(pattern_pop, content, re.DOTALL)
    if m3:
        content = content.replace(m3.group(1), NEW_POPULATE_FIX.strip())
        print("Replaced populate_debit_chain.")
        
    with open(FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_frontend_fix()
