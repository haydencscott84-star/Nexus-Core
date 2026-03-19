import re

TARGET_FILE = "/root/trader_dashboard.py"

# CORRECTED INDENTATION (4 spaces for def, 8 for body)
NEW_UPDATE_METHOD = """    def _update_delta_safe(self):
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

    # Regex to find the mis-indented block
    # Match the 12-space indented version visible in logs
    # Pattern: \s{12}def _update_delta_safe
    print("Replacing severe indentation error...")
    
    # We'll use a broader regex just in case
    content = re.sub(
        r"\s+def _update_delta_safe\(self\):.*?(?=\n\s+def|\n\s+async def|\n\s+class|\nif __name__)", 
        NEW_UPDATE_METHOD, 
        content, 
        flags=re.DOTALL
    )

    print("Writing file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
