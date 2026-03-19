
# PATCH PHASE 17 FRONTEND
# 1. Update Compose to include IV Status
# 2. Update fetch_chain to parse IV/IVR and coloring
# 3. Update populate_debit_chain to use IVR for Prob Adj column

FILE = "nexus_debit_downloaded.py"

NEW_COMPOSE_SNIPPET = r'''
        with Horizontal(id="control_bar"):
            yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")
            yield Label("IV: --% | IVR: --", id="lbl_iv_status", classes="control-item")
            yield Select.from_values(["CALL", "PUT"], allow_blank=False, value="CALL", id="type_select", classes="control-item")
'''

NEW_FETCH = r'''
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
                
                # Update Header
                color = "white"
                if ivr < 30: color = "bold green"
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

NEW_POPULATE = r'''
    def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):
        table = self.query_one("#chain_table", DataTable)
        table.clear(columns=True)
        # Headers: Added PROB. ADJ.
        table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E")
        # NOTE: B/E moved to end or keep consistent? User didn't specify order, but columns match add_columns.
        
        if not chain_data:
            self.log_msg("No spreads returned. Check Strike/Width.")
            return

        cur_price = self.current_spy_price
        if cur_price <= 0: cur_price = 0.01 
        
        # Prob Adj Logic
        if ivr < 30: 
            prob_txt = "[bold green]Boost (+)[/]"
        elif ivr > 50:
            prob_txt = "[bold red]Drag (-)[/]"
        else:
            prob_txt = "Neutral"

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
                
                l_str = f"{l_strike:.0f}"
                s_str = f"{s_strike:.0f}"
                
                is_call = l_strike < s_strike
                if is_call: 
                    be = l_strike + debit
                    dist_pct = ((be - cur_price) / cur_price) * 100
                else: 
                    be = l_strike - debit
                    dist_pct = ((cur_price - be) / cur_price) * 100
                    
                if dist_pct <= 0: dist_style = "[bold green]"
                elif dist_pct < 0.5: dist_style = "[bold yellow]"
                else: dist_style = "[white]"
                    
                roc_style = "bold green" if max_roc > 80 else "bold yellow"
                
                row = [
                    s["expiry"], str(s["dte"]),
                    f"{l_str} (L)", f"{s_str} (S)",
                    f"${debit:.2f}", 
                    f"{dist_style}{dist_pct:.2f}%[/]",
                    prob_txt, # PROB ADJ (Same for all rows as it's regime based)
                    Text(f"{max_roc:.1f}%", style=roc_style),
                    f"{be:.2f}"
                ]
                
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                table.add_row(*row, key=key)
                
            except Exception as e:
                self.log_msg(f"Error parsing spread row: {e}")

        self.log_msg(f"Showing {len(chain_data)} Debit Spreads (IVR {ivr:.0f}).")
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    # 1. Update Compose: We define a logic to replace the first few lines of compose
    if 'with Horizontal(id="control_bar"):' in content:
        # We replace the yield block
        # Find: yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")
        # Replace up to Select.from_values...
        # Wait, regex is safer.
        import re
        # Find the block inside control_bar
        # Matches: yield Label("ðŸ ‹ NEXUS DEBIT" ... yield Select.from_values
        pattern = r'(yield Label\("ðŸ ‹ NEXUS DEBIT".*?)(yield Select)'
        # Replacing with NEW_COMPOSE_SNIPPET lines logic is tricky via regex group internal.
        # Let's just replace the whole compose Horizontal block text we know exists.
        
        old_header = 'yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")'
        if old_header in content and 'yield Label("IV:' not in content:
            new_header = 'yield Label("ðŸ ‹ NEXUS DEBIT", classes="control-item")\n            yield Label("IV: --% | IVR: --", id="lbl_iv_status", classes="control-item")'
            content = content.replace(old_header, new_header)
            print("Updated Compose with IV Label.")
            
    # 2. Replace fetch_chain
    if "async def fetch_chain(self):" in content:
        # Find method block
        pattern = r"(    async def fetch_chain.*?)(?=\n    (?:async )?def |# END|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            content = content.replace(match.group(1), NEW_FETCH.strip())
            print("Replaced fetch_chain.")

    # 3. Replace populate_debit_chain
    if "def populate_debit_chain" in content:
        pattern = r"(    def populate_debit_chain.*?)(?=\n    (?:async )?def |# END|\Z)"
        match = re.search(pattern, content, re.DOTALL)
        if match:
             content = content.replace(match.group(1), NEW_POPULATE.strip())
             print("Replaced populate_debit_chain.")
             
    with open(FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch()
