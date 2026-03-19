
import re

DEBIT_FILE = "nexus_debit.py"
SPREADS_FILE = "nexus_spreads.py"

# --- HELPER: STRIKE PARSING logic for filter ---
FILTER_LOGIC = """
                # FILTER: Check if this is a {TYPE} Spread
                # Short Sym: SPY 250116C500 -> Strike 500
                try:
                    def get_strike(s):
                         # Format: ...C500 or ...P500
                         # Regex: [CP]([\d.]+)$
                         import re
                         m = re.search(r'[CP]([\d.]+)$', s)
                         return float(m.group(1)) if m else 0
                    
                    s_str = short_sym.split(' ')[-1]
                    l_str = long_sym.split(' ')[-1]
                    k_short = get_strike(s_str)
                    k_long = get_strike(l_str)
                    
                    is_put = "P" in s_str
                    is_credit = False
                    
                    if is_put:
                        # Put Credit: Sell High (Short), Buy Low (Long) -> Short > Long
                        if k_short > k_long: is_credit = True
                    else:
                        # Call Credit: Sell Low (Short), Buy High (Long) -> Short < Long
                        if k_short < k_long: is_credit = True
                        
                    # Filter based on App Type
                    TARGET_IS_CREDIT = {IS_CREDIT_FLAG} 
                    if is_credit != TARGET_IS_CREDIT:
                        continue # Skip incorrect spread type
                except: pass
"""

def patch_debit():
    with open(DEBIT_FILE, 'r') as f: content = f.read()

    # 1. Enable raw=True
    content = content.replace('"cmd": "GET_CHAIN"', '"cmd": "GET_CHAIN", "raw": True')

    # 2. Uncomment Workers
    # self.run_worker(self.account_data_loop) # TODO: Re-enable
    content = content.replace("# self.run_worker(self.account_data_loop)", "self.run_worker(self.account_data_loop)")
    content = content.replace("# self.run_worker(self.fetch_managed_spreads_loop)", "self.run_worker(self.fetch_managed_spreads_loop)")
    
    # 3. Inject update_positions (It was missing/placeholder in previous read?)
    # Wait, the previous read didn't show update_positions method in nexus_debit.py!
    # I need to ADD it.
    
    # I'll create a minimal update_positions that includes the loop and filter.
    # Logic extracted from nexus_spreads.py but specific to Debit.
    
    NEW_UPDATE_POS = """
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        pos_map = {p.get("Symbol"): p for p in positions}
        processed_syms = set()
        
        # Managed Spreads
        for short_sym, spread_data in self.managed_spreads.items():
            long_sym = spread_data.get("long_sym")
            if short_sym in pos_map and long_sym in pos_map:
                # FILTER (DEBIT)
                try:
                    def get_strike(s):
                         import re
                         m = re.search(r'[CP]([\d.]+)$', s)
                         return float(m.group(1)) if m else 0
                    s_str = short_sym.split(' ')[-1]; l_str = long_sym.split(' ')[-1]
                    k_short = get_strike(s_str); k_long = get_strike(l_str)
                    is_put = "P" in s_str
                    is_credit = (k_short > k_long) if is_put else (k_short < k_long)
                    if is_credit: continue # Skip Credit Spreads
                except: pass

                p_s = pos_map[short_sym]; p_l = pos_map[long_sym]
                qty = p_s.get("Quantity", 0)
                pl = float(p_s.get("UnrealizedProfitLoss", 0)) + float(p_l.get("UnrealizedProfitLoss", 0))
                val = float(p_s.get("MarketValue", 0)) + float(p_l.get("MarketValue", 0))
                
                table.add_row("DEBIT SPREAD", str(qty), f"${pl:.2f}", f"${val:.2f}", f"{spread_data.get('stop_trigger','-')}")
                processed_syms.add(short_sym); processed_syms.add(long_sym)
    """
    
    # Insert before on_mount or at end of class
    if "def update_positions" not in content:
        # Insert before on_mount
        mount_idx = content.find("async def on_mount")
        content = content[:mount_idx] + NEW_UPDATE_POS + "\n    " + content[mount_idx:]
    
    # Also need account_data_loop and fetch_managed_spreads_loop methods if they are missing?
    # Checked file: they seem missing in the `nexus_debit.py` I read earlier?
    # Wait, I read `nexus_debit.py` in Step 1302 and it ended at line 428.
    # It DID NOT have `account_data_loop` or `fetch_managed_spreads_loop` implemented!
    # It only had `run_worker` calls for them commented out.
    
    # So I must ADD these methods.
    
    MISSING_METHODS = """
    async def account_data_loop(self):
        while True:
            try:
                topic, msg = await self.acct_sock.recv_multipart()
                import json
                data = json.loads(msg)
                positions = data.get("positions", [])
                eq = float(data.get("total_account_value", 0))
                self.account_metrics["equity"] = eq
                pl = sum([float(p.get("UnrealizedProfitLoss", 0)) for p in positions])
                pl_pct = (pl / eq * 100) if eq != 0 else 0.0
                self.query_one("#acct_display").update(f"P/L: ${pl:.0f} ({pl_pct:+.1f}%)")
                self.update_positions(positions)
            except: pass
            
    async def fetch_managed_spreads_loop(self):
        while True:
            try:
                await self.req_sock.send_json({"cmd": "GET_MANAGED_SPREADS"})
                if await self.req_sock.poll(2000):
                    reply = await self.req_sock.recv_json()
                    if reply.get("status") == "ok":
                        sl = reply.get("spreads", [])
                        self.managed_spreads = {s["short_sym"]: s for s in sl if "short_sym" in s}
            except: pass
            await asyncio.sleep(2)
    """
    
    mount_idx = content.find("async def on_mount")
    content = content[:mount_idx] + MISSING_METHODS + "\n    " + content[mount_idx:]

    with open(DEBIT_FILE, 'w') as f: f.write(content)
    print("Patched nexus_debit.py")

def patch_spreads():
    with open(SPREADS_FILE, 'r') as f: content = f.read()
    
    # Inject Filtering Logic into update_positions
    # Find the start of the loop: `if short_sym in pos_map and long_sym in pos_map:`
    marker = "if short_sym in pos_map and long_sym in pos_map:"
    
    logic = FILTER_LOGIC.replace("{TYPE}", "Credit").replace("{IS_CREDIT_FLAG}", "True")
    
    if marker in content:
        # We assume 16 spaces of indentation (inside method, inside loop, inside if)
        # Actually indentation in file is variable. 
        # Let's verify indentation of 'marker'.
        idx = content.find(marker)
        # Scan back to find newline
        nl = content.rfind("\n", 0, idx)
        indent = content[nl+1:idx]
        
        # Apply indentation to logic
        indented_logic = "\n".join([indent + "    " + line.strip() for line in logic.split("\n") if line.strip()])
        
        # Insert AFTER marker result
        # Actually, insert inside the `if` block, at the top.
        replace_with = marker + "\n" + indented_logic
        content = content.replace(marker, replace_with)
        print("Patched nexus_spreads.py with Credit Filter.")
    else:
        print("Could not find update_positions loop in nexus_spreads.py")

    with open(SPREADS_FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_debit()
    patch_spreads()
