
import re
import sys

# PATCH V2: Add WIN% to Nexus Debit (Populate Chain)
TARGET_FILE = "/root/nexus_debit.py"

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()
            
        # 1. Update Columns Header
        # Target: table.add_columns("EXPIRY", ... "B/E")
        old_cols = 'table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E")'
        new_cols = 'table.add_columns("EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %")'
        
        if old_cols in content:
            content = content.replace(old_cols, new_cols)
            print("SUCCESS: Columns Header updated.")
        else:
            print("WARNING: Columns Header NOT FOUND. Check spacing/quotes.")
            
        # 2. Update Row Logic
        # We match the entire row definition block
        # Use simple string match if possible, but regex for safety with formatting
        
        old_row_block = r'row = \[\s+s\["expiry"\],.+?Text\(f"\{max_roc:.1f\}%", style=roc_style\),\s+f"\{be:.2f\}"\s+\]'
        
        # New block has logic for win_pct
        new_logic = """
                 # Win % (Delta Proxy)
                 l_delta = 0.0
                 try:
                     if 'greeks' in s: l_delta = float(s['greeks'].get('delta', 0))
                     elif 'delta' in s: l_delta = float(s['delta'])
                     elif 'long_leg' in s: l_delta = float(s['long_leg'].get('greeks',{}).get('delta',0))
                 except: pass
                 win_str = f"{abs(l_delta*100):.0f}%" # if l_delta != 0 else "-"

                 row = [
                     s["expiry"], str(s["dte"]),
                     f"{l_strike:.0f} (L)", f"{s_strike:.0f} (S)",
                     f"${debit:.2f}",
                     dist_str,
                     prob_txt,
                     Text(f"{max_roc:.1f}%", style=roc_style),
                     f"{be:.2f}",
                     win_str
                 ]"""

        # Perform Regex Sub
        match = re.search(old_row_block, content, re.DOTALL)
        if match:
             content = content[:match.start()] + new_logic + content[match.end():]
             print("SUCCESS: Row Logic updated.")
        else:
             print("ERROR: Row Logic Regex failed match.")
             # Debug hint
             print("--- Snippet of file around 'row =' ---")
             start = content.find("row = [")
             if start != -1:
                 print(content[start:start+200])
        
        with open(TARGET_FILE, 'w') as f:
            f.write(content)

    except Exception as e:
        print(f"PATCH ERROR: {e}")

if __name__ == "__main__":
    apply_patch()
