
import re

# V3 Patch: Handles READY/HEARTBEAT + proper logging
# We define specific templates for Credit (Spreads) vs Debit to get correct Titles

SPREADS_METHOD = """    async def announce_status(self, reason="UPDATE"):
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            try:
                table = self.query_one("#positions_table", DataTable)
                for row_key in table.rows:
                    row_data = table.get_row(row_key)
                    
                    def to_str(item):
                        if hasattr(item, "plain"): return item.plain
                        return str(item)
                    
                    # Headers: STRATEGY, STRIKES, DTE, QTY, P/L OPEN ...
                    strat = to_str(row_data[0])
                    strikes = to_str(row_data[1])
                    qty = to_str(row_data[3])
                    stop = to_str(row_data[6])
                    
                    pos_str = f"**{strat}** {strikes} (x{qty})\\nSTOP: {stop} | PT: 50% Max | **ARMED**"
                    positions.append(pos_str)
            except Exception as e:
                self.log_msg(f"Announce Data Error: {e}")

            if not positions:
                if reason in ["LAUNCH", "READY"]:
                    msg = "**Nexus Credit Sniper Online**\\nActive Positions: None."
                elif reason in ["MARKET_OPEN", "MARKET_CLOSE", "HEARTBEAT"]:
                    msg = f"**Nexus Credit Status ({reason})**\\nSystem Active. No Open Positions."
                else: return
            else:
                pos_block = "\\n".join(positions)
                msg = f"**Nexus Credit Status ({reason})**\\n{pos_block}"
            
            async with aiohttp.ClientSession() as session:
                payload = {"content": msg}
                async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                    if resp.status not in [200, 204]:
                        self.log_msg(f"Discord Post Error: {resp.status}")
        except Exception as e:
            self.log_msg(f"Announce Error: {e}")
"""

DEBIT_METHOD = """    async def announce_status(self, reason="UPDATE"):
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            try:
                table = self.query_one("#positions_table", DataTable)
                for row_key in table.rows:
                    row_data = table.get_row(row_key)
                    
                    def to_str(item):
                        if hasattr(item, "plain"): return item.plain
                        return str(item)
                    
                    strat = to_str(row_data[0])
                    strikes = to_str(row_data[1])
                    qty = to_str(row_data[3])
                    stop = to_str(row_data[6])
                    
                    pos_str = f"**{strat}** {strikes} (x{qty})\\nSTOP: {stop} | PT: 50% Max | **ARMED**"
                    positions.append(pos_str)
            except Exception as e:
                self.log_msg(f"Announce Data Error: {e}")

            if not positions:
                if reason in ["LAUNCH", "READY"]:
                    msg = "**Nexus Debit Sniper Online**\\nActive Positions: None."
                elif reason in ["MARKET_OPEN", "MARKET_CLOSE", "HEARTBEAT"]:
                    msg = f"**Nexus Debit Status ({reason})**\\nSystem Active. No Open Positions."
                else: return
            else:
                pos_block = "\\n".join(positions)
                msg = f"**Nexus Debit Status ({reason})**\\n{pos_block}"
            
            async with aiohttp.ClientSession() as session:
                payload = {"content": msg}
                async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                    if resp.status not in [200, 204]:
                        self.log_msg(f"Discord Post Error: {resp.status}")
        except Exception as e:
            self.log_msg(f"Announce Error: {e}")
"""

def patch_file(path, new_method_code):
    try:
        with open(path, 'r') as f:
            content = f.readlines()
            
        new_lines = []
        skip = False
        patched = False
        
        target = "    async def announce_status(self, reason="
        
        for line in content:
            if target in line:
                new_lines.append(new_method_code)
                skip = True
                patched = True
                continue
                
            if skip:
                if line.strip() and not line.startswith('    '):
                    skip = False
                    new_lines.append(line)
                elif re.match(r'    (async )?def ', line):
                    skip = False
                    new_lines.append(line)
                continue
                
            new_lines.append(line)
            
        with open(path, 'w') as f:
            f.writelines(new_lines)
            
        if patched: print(f"SUCCESS: {path}")
        else: print(f"NOT_FOUND: {path}")

    except Exception as e:
        print(f"ERROR {path}: {e}")

if __name__ == "__main__":
    patch_file('/root/nexus_spreads.py', SPREADS_METHOD)
    patch_file('/root/nexus_debit.py', DEBIT_METHOD)
