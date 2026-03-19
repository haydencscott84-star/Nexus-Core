
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f:
        content = f.read()

    # New WYSIWYG announce_status implementation
    new_method = """
    async def announce_status(self, reason="UPDATE"):
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            # WYSIWYG: Pull directly from table
            try:
                table = self.query_one("#positions_table", DataTable)
                # Textual DataTable rows are keyed or list-based. 
                # We iterate row_values to get the renderables/text.
                for row_key in table.rows:
                    row_data = table.get_row(row_key)
                    # Headers: STRATEGY, STRIKES, DTE, QTY, P/L OPEN, EXPOSURE, STOP, PT
                    # Row: [0]=Strat, [1]=Strikes, [2]=Dte, [3]=Qty, [4]=PL, [5]=Exp, [6]=Stop, [7]=PT
                    
                    # Convert Rich Text to string if needed
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
                # If table query fails (app starting?), ignore
                pass

            if not positions:
                if reason == "LAUNCH":
                    msg = (f"**Nexus Credit Sniper Online**\\n"
                           f"Active Positions: None.")
                else: 
                     if reason in ["MARKET_OPEN", "MARKET_CLOSE"]:
                         msg = f"**Nexus Credit Status ({reason})**\\nSystem Active. No Open Positions."
                     else: return
            else:
                pos_block = "\\n".join(positions)
                msg = f"**Nexus Credit Status ({reason})**\\n{pos_block}"
            
            async with aiohttp.ClientSession() as session:
                payload = {"content": msg}
                async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                    pass
        except Exception as e:
            pass
    """

    # We need to find the old announce_status and replace it
    # It starts with 'async def announce_status(self, reason="UPDATE"):' 
    # and ends before the next method. 
    # But doing regex replacement on indentation is risky remote.
    # Safe bet: We verify the unique signature exists, then locate lines.
    
    lines = content.split('\n')
    start_idx = -1
    end_idx = -1
    
    # Simple parser to find method block
    for i, line in enumerate(lines):
        if 'async def announce_status(self, reason=' in line:
            start_idx = i
            continue
        if start_idx != -1 and i > start_idx and 'def ' in line and line.strip().startswith('def') or line.strip().startswith('async def'):
            # Found next method
            if line.startswith('    ') or line.startswith('\t'):
                # Checks if it's an inner function? No, class methods usually start with 4 spaces.
                # But 'def' check is fuzzy. A safer way is indentation check.
                pass
    
    # Let's try string replacement chunk since we know the header
    header = 'async def announce_status(self, reason="UPDATE"):'
    if header in content:
        # We need to be careful about where it ends. 
        # Easier strategy: Append the new method at the END of the class or file? 
        # No, inheritance/overriding order matters.
        
        # We will iterate lines.
        new_lines = []
        skip = False
        replaced = False
        
        for i, line in enumerate(lines):
            if 'async def announce_status(self, reason=' in line:
                if not replaced:
                    new_lines.append(new_method)
                    skip = True
                    replaced = True
                continue
            
            if skip:
                # We skip until we see a line with equal or less indentation than the method def (4 spaces)
                # But empty lines don't count.
                if line.strip() and not line.startswith('    '):
                    # Found end of method (class level dedent or new class) or next method?
                    # Methods usually have 4 spaces. Classes 0.
                    # Wait, if next line is '    async def next_method', it has same indent.
                    pass
                
                # Check if it looks like a new method start
                if line.strip().startswith('def ') or line.strip().startswith('async def '):
                    # We verify indent level.
                    indent = len(line) - len(line.lstrip())
                    if indent == 4:
                        skip = False
                        new_lines.append(line)
                        continue
                
                # If we are skipping, we just don't add.
                continue
            
            new_lines.append(line)
            
        with open(path, 'w') as f:
            f.write('\n'.join(new_lines))
        print("PATCH_SUCCESS")
        
    else:
        print("METHOD_NOT_FOUND")

except Exception as e:
    print(f"ERROR: {e}")
