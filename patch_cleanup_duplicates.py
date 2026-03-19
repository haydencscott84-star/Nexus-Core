
# PATCH CLEANUP DUPLICATES
# Removes multiple copies of fetch_chain and on_fetch

FILE = "nexus_debit_downloaded.py"

CLEAN_BLOCK = r'''    @on(Button.Pressed, "#fetch_btn")
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
                if ivr < 30: color = "bold yellow"
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

def cleanup():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    start_idx = -1
    end_idx = -1
    
    # Check for start marker: @on(Button.Pressed, "#fetch_btn")
    # Note: Indentation might vary in the messed up file, so strip()
    for i, line in enumerate(lines):
        if '@on(Button.Pressed, "#fetch_btn")' in line:
            start_idx = i
            break
            
    # Check for end marker: @on(Button.Pressed, "#refresh_btn")
    for i, line in enumerate(lines):
        if i > start_idx and '@on(Button.Pressed, "#refresh_btn")' in line:
            end_idx = i
            break
            
    if start_idx != -1 and end_idx != -1:
        print(f"Replacing duplicates from line {start_idx} to {end_idx}...")
        
        # Construct new lines
        final_lines = lines[:start_idx] + [CLEAN_BLOCK] + lines[end_idx:]
        
        with open(FILE, 'w') as f: f.writelines(final_lines)
        print("Cleanup successful.")
    else:
        print(f"Could not find range. Start: {start_idx}, End: {end_idx}")

if __name__ == "__main__":
    cleanup()
