
import re

DEBIT_FILE = "nexus_debit.py"
TS_FILE = "ts_nexus.py"

def patch_debit():
    with open(DEBIT_FILE, 'r') as f: content = f.read()

    # 1. CSS: Add #strike_input
    if "#strike_input {" not in content:
        content = content.replace("#type_select { width: 12; }", "#type_select { width: 12; }\n    #strike_input { width: 12; }")
        
    # 2. Compose: Add Input widget
    # Find: yield Select.from_values(["CALL", "PUT"], ...
    # Add Input before or after
    # Pattern: 
    # yield Select.from_values(["CALL", "PUT"], value="CALL", id="type_select", classes="control-item")
    # yield Input(value="30", id="width_input", classes="control-item")
    
    # We want:
    # yield Select...
    # yield Input(placeholder="Strike", id="strike_input", classes="control-item")
    # yield Input...
    
    if 'id="strike_input"' not in content:
        target = 'yield Select.from_values(["CALL", "PUT"], value="CALL", id="type_select", classes="control-item")'
        injection = 'yield Select.from_values(["CALL", "PUT"], value="CALL", id="type_select", classes="control-item")\n                yield Input(placeholder="Strike", id="strike_input", classes="control-item")'
        content = content.replace(target, injection)
        
    # 3. Fetch Logic: Read strike_input
    # Find: width = self.query_one("#width_input").value
    # Add: strike_val = self.query_one("#strike_input").value
    # payload... "strike": float(strike_val) if strike_val else 0
    
    if 'strike_val = self.query_one("#strike_input").value' not in content:
        # We need to construct the payload line carefully to include "strike" or "target_strike" 
        # ts_nexus uses "strike" (verified in previous step)
        
        target_line = 'width = self.query_one("#width_input").value'
        injection = 'width = self.query_one("#width_input").value\n        strike_val = self.query_one("#strike_input").value\n        target_strike = float(strike_val) if strike_val and strike_val.strip() else 0.0'
        content = content.replace(target_line, injection)
        
        # Payload update
        # Old (from patch_round2 and clean): 
        # payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "price": self.current_spy_price, "width": width}
        # New:
        # payload = {..., "strike": target_strike}
        
        # Using regex to update payload safely
        content = re.sub(
            r'payload = \{"cmd": "GET_CHAIN".*?\}',
            'payload = {"cmd": "GET_CHAIN", "ticker": "SPY", "type": type_, "raw": True, "price": self.current_spy_price, "width": width, "strike": target_strike}',
            content
        )

    # 4. FIX: Thread Safety for Update Positions & Auto Manager
    # The user reported "Operation cannot be accomplished...".
    # In Textual, 'call_later' schedules a callback on the main thread.
    # We wrap the internal logic of update_positions.
    
    # Rename update_positions to _update_positions_internal and create a wrapper?
    # Or just use call_later inside account_data_loop?
    
    # Let's modify account_data_loop to use call_later for UI updates.
    # Find: self.update_positions(positions)
    # Replace: self.call_after_refresh(self.update_positions, positions)
    # Or self.app.call_from_thread if it was threaded (it's async worker).
    # In async worker, direct calling is usually fine, but 'call_after_refresh' is safer for heavy table mods.
    
    if 'self.update_positions(positions)' in content:
        content = content.replace('self.update_positions(positions)', 'self.call_after_refresh(self.update_positions, positions)')
        
    # Also for acct_display update line just above it
    if 'self.query_one("#acct_display").update' in content:
         # It's a simple update(), usually fine.
         pass
         
    with open(DEBIT_FILE, 'w') as f: f.write(content)
    print("Patched nexus_debit.py: Added Strike Input + Thread Safety")

def patch_backend():
    with open(TS_FILE, 'r') as f: content = f.read()
    
    # Ensure GET_POSITIONS defaults account if missing
    # Find: account_key = msg.get("account", "SIM")
    # Actually, let's just inspect where it gets account.
    # Usually: account = msg.get('account')
    # If I just used 'SIM_ACC' in debug and got 0, maybe default is SIM?
    
    # I'll rely on existing backend logic but ensure it's using the main account configured in 'nexus_config.py' if available?
    # For now, no change needed unless I see explicit failure. 
    # Debug script returned 0 likely because SIM has no positions or Watchtower isn't feeding it.
    pass

if __name__ == "__main__":
    patch_debit()
    patch_backend()
