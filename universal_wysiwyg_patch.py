
import sys
import re

# --- TEMPLATES ---

SPREADS_METHOD = """    async def announce_status(self, reason="UPDATE"):
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            # WYSIWYG: Pull directly from table
            try:
                table = self.query_one("#positions_table", DataTable)
                for row_key in table.rows:
                    row_data = table.get_row(row_key)
                    # Headers: STRATEGY, STRIKES, DTE, QTY, P/L OPEN, EXPOSURE, STOP, PT
                    # [0]=Strat, [1]=Strikes, [2]=Dte, [3]=Qty, [4]=PL, [5]=Exp, [6]=Stop, [7]=PT
                    
                    def to_str(item):
                        if hasattr(item, "plain"): return item.plain
                        return str(item)
                        
                    strat = to_str(row_data[0])
                    strikes = to_str(row_data[1])
                    qty = to_str(row_data[3])
                    stop = to_str(row_data[6])
                    
                    pos_str = f"**{strat}** {strikes} (x{qty})\\nSTOP: {stop} | PT: 50% Max | **ARMED**"
                    positions.append(pos_str)
            except: pass

            if not positions:
                if reason == "LAUNCH":
                    msg = "**Nexus Credit Sniper Online**\\nActive Positions: None."
                elif reason in ["MARKET_OPEN", "MARKET_CLOSE"]:
                    msg = f"**Nexus Credit Status ({reason})**\\nSystem Active. No Open Positions."
                else: return
            else:
                pos_block = "\\n".join(positions)
                msg = f"**Nexus Credit Status ({reason})**\\n{pos_block}"
            
            async with aiohttp.ClientSession() as session:
                payload = {"content": msg}
                async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp: pass
        except: pass
"""

DEBIT_METHOD = """    async def announce_status(self, reason="UPDATE"):
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            # WYSIWYG: Pull directly from table
            try:
                table = self.query_one("#positions_table", DataTable)
                for row_key in table.rows:
                    row_data = table.get_row(row_key)
                    # Headers: STRATEGY, STRIKES, DTE, QTY, P/L OPEN, EXPOSURE, STOP, PT
                    # [0]=Strat, [1]=Strikes, [2]=Dte, [3]=Qty, [4]=PL, [5]=Exp, [6]=Stop, [7]=PT
                    
                    def to_str(item):
                        if hasattr(item, "plain"): return item.plain
                        return str(item)
                        
                    strat = to_str(row_data[0])
                    strikes = to_str(row_data[1])
                    qty = to_str(row_data[3])
                    stop = to_str(row_data[6])
                    
                    pos_str = f"**{strat}** {strikes} (x{qty})\\nSTOP: {stop} | PT: 50% Max | **ARMED**"
                    positions.append(pos_str)
            except: pass

            if not positions:
                if reason == "LAUNCH":
                    msg = "**Nexus Debit Sniper Online**\\nActive Positions: None."
                elif reason in ["MARKET_OPEN", "MARKET_CLOSE"]:
                    msg = f"**Nexus Debit Status ({reason})**\\nSystem Active. No Open Positions."
                else: return
            else:
                pos_block = "\\n".join(positions)
                msg = f"**Nexus Debit Status ({reason})**\\n{pos_block}"
            
            async with aiohttp.ClientSession() as session:
                payload = {"content": msg}
                async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp: pass
        except: pass
"""

def patch_file(path, new_method_code):
    try:
        with open(path, 'r') as f:
            content = f.readlines()
            
        new_lines = []
        skip = False
        patched = False
        
        # We assume 4-space indent for class methods
        method_sig = "    async def announce_status(self,"
        
        for line in content:
            if method_sig in line:
                new_lines.append(new_method_code)
                skip = True
                patched = True
                continue
                
            if skip:
                # If we encounter a new method definition (at class level indentation), stop skipping
                # Regex for "    def" or "    async def"
                if re.match(r'    (async )?def ', line):
                    skip = False
                    new_lines.append(line)
                # Or if we hit dedent (less than 4 spaces, but not empty/comment)
                elif line.strip() and not line.startswith('    '):
                    skip = False
                    new_lines.append(line)
                continue
                
            new_lines.append(line)
            
        with open(path, 'w') as f:
            f.writelines(new_lines)
            
        if patched:
            print(f"SUCCESS: {path}")
        else:
            print(f"NOT_FOUND: {path} (Method signature not matched)")
            
    except Exception as e:
        print(f"ERROR {path}: {e}")

if __name__ == "__main__":
    patch_file('/root/nexus_spreads.py', SPREADS_METHOD)
    patch_file('/root/nexus_debit.py', DEBIT_METHOD)
