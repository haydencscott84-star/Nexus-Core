
# PATCH MANUAL FETCH LOGIC
# Target: nexus_debit_downloaded.py
DEBIT_FILE = "nexus_debit_downloaded.py"

# Redefined populate_debit_chain to accept target_strike and assume it matches if provided
NEW_POPULATE = r"""
    def populate_debit_chain(self, chain_data, width, target_strike=0.0):
        table = self.query_one("#chain_table", DataTable)
        table.clear()
        
        # 1. IDENTIFY CANDIDATES
        long_candidates = []
        
        # If target_strike is set (manual mode), Find closest matching strike
        if target_strike > 0:
            # Find exact or closest match
            # Tolerance 1.0
            matches = [x for x in chain_data if abs(float(x['strike']) - target_strike) < 1.0]
            if matches:
                long_candidates = matches
            else:
                # Relaxed search?
                long_candidates = []
        else:
            # Default: Delta 0.70 Search
            for opt in chain_data:
                delta = abs(float(opt.get('delta', 0)))
                if 0.65 <= delta <= 0.80:
                    long_candidates.append(opt)
        
        # 2. BUILD SPREADS
        spread_setups = []
        for long_leg in long_candidates:
            l_strike = float(long_leg['strike'])
            delta_val = float(long_leg['delta'])
            
            # Target Short
            if delta_val < 0: # PUT (though we usually filter for correct type in backend request)
                 t_short = l_strike - width
            else: # CALL
                 t_short = l_strike + width
            
            # Find Short Leg
            short_leg = next((x for x in chain_data if abs(float(x['strike']) - t_short) < 0.5 and x['expiry'] == long_leg['expiry']), None)
            
            if short_leg:
                debit = float(long_leg['ask']) - float(short_leg['bid'])
                if debit <= 0: continue
                
                max_profit = width - debit
                roc = (max_profit / debit) * 100
                
                spread_setups.append({
                    "long": long_leg,
                    "short": short_leg,
                    "debit": debit,
                    "profit": max_profit,
                    "roc": roc
                })
        
        # 3. SORT
        spread_setups.sort(key=lambda x: x['roc'], reverse=True)
        top_picks = spread_setups[:20]
        
        # 4. POPULATE
        for s in top_picks:
            l = s['long']; sh = s['short']
            roc = s['roc']
            roc_style = "bold green" if roc > 80 else "bold yellow"
            
            row = [
                l["expiry"], str(l["dte"]), 
                f"{l['strike']} (L)", f"{sh['strike']} (S)",
                f"${s['debit']:.2f}", f"${s['profit']:.2f}",
                Text(f"{roc:.1f}%", style=roc_style),
                f"{float(l['delta']):.2f}"
            ]
            
            key = f"{l['symbol']}|{sh['symbol']}|{s['debit']}|{l['strike']}|{sh['strike']}|{width}"
            table.add_row(*row, key=key)
            
        self.log_msg(f"Showing {len(top_picks)} results (Manual Strike: {target_strike if target_strike > 0 else 'Auto'}).")
"""

# We also need to update fetch_chain to PASS the target_strike to populate_debit_chain
NEW_FETCH_CHAIN = r"""
    async def fetch_chain(self):
        btn = self.query_one("#fetch_btn")
        btn.disabled = True
        btn.label = "SCANNING..."
        
        type_ = self.query_one("#type_select").value
        width_val = self.query_one("#width_input").value
        width = float(width_val) if width_val else 10.0
        
        strike_val = self.query_one("#strike_input").value
        target_strike = float(strike_val) if strike_val and strike_val.strip() else 0.0

        if target_strike > 0:
             self.log_msg(f"Fetching Manual Setup: Strike {target_strike} Width {width}...")
        else:
             self.log_msg("Scanning for Delta 0.70 Setups...")
        
        payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "price": self.current_spy_price, "width": width, "strike": target_strike}
        
        try:
            await self.req_sock.send_json(payload)
            reply = await self.req_sock.recv_json()
            if reply.get("status") == "ok":
                # PASS target_strike here!
                self.populate_debit_chain(reply.get("data", []), width, target_strike)
            else:
                self.log_msg(f"Error: {reply.get('msg')}")
        except Exception as e:
            self.log_msg(f"Connection Error: {e}")
            
        btn.disabled = False
        btn.label = "SCAN SETUP"
"""


def patch_manual_fetch():
    with open(DEBIT_FILE, 'r') as f: content = f.read()
    
    # 1. Replace populate_debit_chain argument signature if needed
    # The original signature was: def populate_debit_chain(self, chain_data, width):
    # The new one is: def populate_debit_chain(self, chain_data, width, target_strike=0.0):
    # We replace the whole method.
    
    # Locate boundaries
    pop_start = "def populate_debit_chain(self, chain_data, width):"
    pop_end = "def on_data_table_row_selected(self, event: DataTable.RowSelected):"
    
    if pop_start in content:
        pre, post = content.split(pop_start, 1)
        if pop_end in post:
            body, remainder = post.split(pop_end, 1)
            content = pre + NEW_POPULATE.strip() + "\n    \n    " + pop_end + remainder
            print("Patched populate_debit_chain")
    
    # 2. Replace fetch_chain to pass the argument
    fetch_start = "async def fetch_chain(self):"
    fetch_end = "@on(Button.Pressed, \"#fetch_btn\")" # Safe end marker? or helper?
    # fetch_chain is usually followed by event handler decorators.
    # In my view_file output, it was followed by on_fetch.
    
    # Actually, let's use the exact content from previous tool output for match if needed.
    # Or just replace the method body logic.
    
    # Safest is strict replacement of known block.
    # "def fetch_chain" ... until ... "@on"
    
    import re
    # Find start of fetch_chain
    m_start = re.search(r'async def fetch_chain\(self\):', content)
    if m_start:
        start_idx = m_start.start()
        # Find next method start (likely @on or def)
        m_end = re.search(r'@on\(Button\.Pressed', content[start_idx:])
        
        if m_end:
            end_idx = start_idx + m_end.start()
            
            # Replace
            new_c = content[:start_idx] + NEW_FETCH_CHAIN.strip() + "\n        \n    " + content[end_idx:]
            content = new_c
            print("Patched fetch_chain")
        else:
            print("Error: Could not find end of fetch_chain")
            
    with open(DEBIT_FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_manual_fetch()
