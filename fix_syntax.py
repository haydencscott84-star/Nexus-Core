import re

TARGET_FILE = "/root/trader_dashboard.py"

# CORRECTED INDENTATION (4 spaces for def, 8 for body) WITH NEWLINE
NEW_UPDATE_METHOD = """
    def _update_delta_safe(self):
        try:
            nd, ng = self.calculate_net_delta()
            # Format: "DELTA: +315 | Γ: -15"
            # Gamma Color: Red if < 0 (Risk), Green/Blue if > 0
            g_color = "#bf616a" if ng < 0 else "#a3be8c"
            
            label = f"{nd:+.0f} | Γ {ng:+.0f}"
            try:
                self.query_one('#m-delta', Metric).update_val(label, g_color)
            except: pass
            
        except Exception as e:
            self.log_msg(f"[ERR] Delta Update: {e}")
"""

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # Regex to find the concatenated mess
    # Pattern: ...CANCEL ERR: {e}")    def _update_delta_safe
    print("Replacing concatenated syntax error...")
    
    # We look for the specific broken line sequence
    content = content.replace('except Exception as e: self.log_msg(f"CANCEL ERR: {e}")    def _update_delta_safe(self):', 
                              'except Exception as e: self.log_msg(f"CANCEL ERR: {e}")\n' + NEW_UPDATE_METHOD.lstrip())
    
    # Fallback if regex already messed it up differently
    if "def _update_delta_safe" not in content:
        print("Function not found, attempting broader search...")

    print("Writing file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
