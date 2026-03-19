
# PATCH DEBIT FETCH LOGIC
# Target: nexus_debit_downloaded.py
# 1. Redefine populate_debit_chain to consume 'spread list' from TS
# 2. Add Guard in fetch_chain for Missing Strike

FILE = "nexus_debit_downloaded.py"

NEW_POPULATE = r'''
    def populate_debit_chain(self, chain_data, width, target_strike=0.0):
        # NOTE: chain_data is now a LIST OF SPREADS from ts_nexus.py
        # Keys: short, long, short_sym, long_sym, raw quotes (bid_short, etc.)
        
        table = self.query_one("#chain_table", DataTable)
        table.clear()
        
        if not chain_data:
            self.log_msg("No spreads returned. Check Strike/Width.")
            return

        for s in chain_data:
            # S = Target/Short Leg (from TS perspective)
            # L = Hedge/Long Leg (from TS perspective)
            
            # For Debit Spread (Buy ITM, Sell OTM):
            # We BUY the 'Short' (Target) leg.
            # We SELL the 'Long' (Hedge) leg.
            
            # Logic: Debit = Ask(Short) - Bid(Long)
            
            try:
                ask_short = float(s.get("ask_short", 0))
                bid_long = float(s.get("bid_long", 0))
                
                # Fallback if raw quotes missing (old ts_nexus?)
                if ask_short == 0 and bid_long == 0:
                    # Retry using credit logic if possible? 
                    # Credit = Bid_Short - Ask_Long.
                    # Debit ~= Ask_Short - Bid_Long.
                    # Approximation: Use Credit * -1? No, spread is wide.
                    # If raw missing, we can't price it accurately.
                    pass

                debit = ask_short - bid_long
                if debit <= 0: debit = 0.01 # Should not happen for valid debit spread
                
                width_val = abs(float(s["short"]) - float(s["long"]))
                max_profit = width_val - debit
                roc = (max_profit / debit) * 100 if debit > 0 else 0
                
                l_strike = s["short"] # user's target strike
                s_strike = s["long"]  # hedge strike
                
                # Styles
                roc_style = "bold green" if roc > 80 else "bold yellow"
                
                row = [
                    s["expiry"], str(s["dte"]),
                    f"{l_strike} (Long)", f"{s_strike} (Short)",
                    f"${debit:.2f}", f"${max_profit:.2f}",
                    Text(f"{roc:.1f}%", style=roc_style),
                    "-" # Delta not available in spread object
                ]
                
                # Key: long_sym|short_sym|debit|l_strike|s_strike|width
                # Mapped: long_sym -> s['short_sym'] (We BUY this)
                #         short_sym -> s['long_sym'] (We SELL this)
                
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{l_strike}|{s_strike}|{width_val}"
                table.add_row(*row, key=key)
                
            except Exception as e:
                self.log_msg(f"Error parsing spread row: {e}")

        self.log_msg(f"Showing {len(chain_data)} Debit Spreads.")
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
        
        # 'raw': True is legacy/ignored by TS now, but we send standard params
        payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "strike": target_strike, "width": width}
        
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
'''

def patch_methods():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    # 1. REPLACE populate_debit_chain
    # Find start/end
    start_pop = -1
    end_pop = -1
    
    for i, line in enumerate(lines):
        if "def populate_debit_chain" in line:
            start_pop = i
        if start_pop != -1 and i > start_pop:
            if "def on_data_table_row_selected" in line:
                end_pop = i
                break
                
    if start_pop != -1 and end_pop != -1:
        # Reconstruct
        new_pop_lines = [l + "\n" for l in NEW_POPULATE.splitlines() if l.strip() != ""] # Wait, splitlines removes \n
        new_pop_lines = [l + "\n" for l in NEW_POPULATE.split("\n") if l] # preserve indent
        
        lines = lines[:start_pop] + new_pop_lines + lines[end_pop:]
        print("Replaced populate_debit_chain")
    else:
        print(f"Failed to find populate_debit_chain boundaries {start_pop} {end_pop}")
        
    # 2. REPLACE fetch_chain
    # To avoid index shift, we should do it in one pass or reload? 
    # Let's reload to be safe or use safe offsets? 
    # Just reload lines object since we modified it? No, lines is a list.
    
    # Let's write file and re-read for second patch
    with open(FILE, 'w') as f: f.writelines(lines)
    
    with open(FILE, 'r') as f: lines = f.readlines()
    start_fetch = -1
    end_fetch = -1
    
    for i, line in enumerate(lines):
        if "async def fetch_chain" in line:
            start_fetch = i
        if start_fetch != -1 and i > start_fetch:
            if "@on(Button" in line: # Usually on_fetch is decorated
                end_fetch = i
                break
            if "async def on_fetch" in line: # if no decorator
                end_fetch = i 
                break
                
    if start_fetch != -1 and end_fetch != -1:
         new_fetch_lines = [l + "\n" for l in NEW_FETCH.split("\n") if l]
         lines = lines[:start_fetch] + new_fetch_lines + lines[end_fetch:]
         with open(FILE, 'w') as f: f.writelines(lines)
         print("Replaced fetch_chain")
    else:
         print(f"Failed to find fetch_chain boundaries {start_fetch} {end_fetch}")

if __name__ == "__main__":
    patch_methods()
