
# PATCH DEBIT SCAN UI & PYTZ
# Target: nexus_debit_downloaded.py
# 1. Fix 'pytz' import error.
# 2. Refine Scan Table (Target Profit, B/E, Max ROC).

import re

FILE = "nexus_debit_downloaded.py"

# --- 1. FIX PYTZ ---
# Inject import at the top
IMPORT_BLOCK = """import sys
import zmq
import zmq.asyncio
import asyncio
import datetime
try:
    import pytz
except ImportError:
    pytz = None
"""

# --- 2. REFINE POPULATE METHOD ---
# We replace the entire method to ensure clean headers and logic.
NEW_POPULATE = r'''
    def populate_debit_chain(self, chain_data, width, target_strike=0.0):
        # NOTE: chain_data is now a LIST OF SPREADS from ts_nexus.py
        # Keys: short, long, short_sym, long_sym, raw quotes (bid_short, etc.)
        
        table = self.query_one("#chain_table", DataTable)
        table.clear()
        
        # [MODIFIED] Headers: TGT PROFIT, B/E, MAX ROC %
        # Was: STRATEGY, STRIKES, DTE, QTY, P/L OPEN, EXPOSURE, STOP, PT
        # No, that's existing positions table.
        # This is chain_table. Columns defined in formatting? 
        # Actually chain_table columns are set in on_mount or re-defined here?
        # Usually defined in on_mount. We might need to update columns dynamically or just map data to them?
        # Let's check on_mount in next step. For now, let's assume we need to RE-DEFINE columns if we change them.
        # Or clear and add columns? 
        
        # Let's re-define columns just in case
        table.clear(columns=True)
        table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "TGT PROFIT", "B/E", "MAX ROC %")

        if not chain_data:
            self.log_msg("No spreads returned. Check Strike/Width.")
            return

        for s in chain_data:
            try:
                ask_short = float(s.get("ask_short", 0))
                bid_long = float(s.get("bid_long", 0))
                
                # Logic: Debit = Ask(Short) - Bid(Long)
                debit = ask_short - bid_long
                if debit <= 0: debit = 0.01 
                
                width_val = abs(float(s["short"]) - float(s["long"]))
                max_profit_theo = width_val - debit
                max_roc = (max_profit_theo / debit) * 100 if debit > 0 else 0
                
                # [MODIFIED LOGIC]
                # TGT PROFIT = 50% of Debit (Bot Target)
                tgt_profit = debit * 0.50
                
                # B/E
                # Call Debit: Long Strike + Debit
                # Put Debit: Long Strike - Debit
                # Check type from symbol? Or assume ITM Long?
                # Nexus Debit is usually Delta 0.70 Long (ITM) + Short (OTM).
                # If Long Strike < Short Strike => CALL (Bull Debit)
                # If Long Strike > Short Strike => PUT (Bear Debit)
                
                l_strike = float(s["short"]) # This is actually 'short' key from TS which is Target/ITM in our logic?
                # Wait, earlier patch: 
                # l_strike = s["short"] # user's target strike (Purchase Leg)
                # s_strike = s["long"]  # hedge strike (Sale Leg)
                # Let's verify strikes.
                # If it's a Call Debit: Buy 700C, Sell 710C. Long leg is 700. Short leg is 710.
                # In TS 'spread' object: 
                # 'short' key was target_strike.
                # 'long' key was hedge.
                
                stk_1 = float(s["short"])
                stk_2 = float(s["long"])
                
                is_call = stk_1 < stk_2 # Lower strike is ITM for Call? 
                # Wait, if target is 700 (ITM) and hedge is 710 (OTM). 700 < 710. Correct.
                # If Put Debit: Buy 700P (ITM), Sell 690P (OTM). 700 > 690.
                
                if stk_1 < stk_2: # CALL
                    be = stk_1 + debit
                else: # PUT
                    be = stk_1 - debit
                
                # Styles
                roc_style = "bold green" if max_roc > 80 else "bold yellow"
                
                row = [
                    s["expiry"], str(s["dte"]),
                    f"{stk_1:.1f} (L)", f"{stk_2:.1f} (S)",
                    f"${debit:.2f}", 
                    f"${tgt_profit:.2f}", # TGT PROFIT
                    f"{be:.2f}",          # B/E
                    Text(f"{max_roc:.1f}%", style=roc_style) # MAX ROC
                ]
                
                key = f"{s['short_sym']}|{s['long_sym']}|{debit}|{stk_1}|{stk_2}|{width_val}"
                table.add_row(*row, key=key)
                
            except Exception as e:
                self.log_msg(f"Error parsing spread row: {e}")

        self.log_msg(f"Showing {len(chain_data)} Debit Spreads.")
'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    # 1. FIX IMPORTS
    # Replace the top imports with our robust block
    if "import sys" in content and "try:\n    import pytz" not in content:
        # Find first few lines
        content = content.replace("import sys\nimport zmq\nimport zmq.asyncio\nimport asyncio\nimport datetime", IMPORT_BLOCK)
        print("Fixed imports.")
    else:
        print("Imports already fixed or pattern mismatch.")
        
    # 2. REPLACE METHOD
    # We use regex to find the method body
    # Using simple split logic for robustness
    if "def populate_debit_chain(self, chain_data, width, target_strike=0.0):" in content:
        # Identify start
        start_marker = "def populate_debit_chain(self, chain_data, width, target_strike=0.0):"
        
        # Identify end (next method)
        # Usually `async def execute_trade` or `on_data_table_row_selected`
        parts = content.split(start_marker)
        if len(parts) > 1:
            pre = parts[0]
            post = parts[1]
            
            # Find next method definition
            # We look for indentation 4 spaces + def/async def
            next_method_match = re.search(r'\n    (?:async )?def ', post)
            if next_method_match:
                end_idx = next_method_match.start()
                remainder = post[end_idx:]
                
                new_content = pre + NEW_POPULATE.strip() + "\n" + remainder
                content = new_content
                print("Replaced populate_debit_chain.")
            else:
                 print("Could not find end of populate_debit_chain.")
    else:
        print("Could not find populate_debit_chain signature.")
        
    with open(FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch()
