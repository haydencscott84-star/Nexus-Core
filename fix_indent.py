import re

TARGET_FILE = "/root/trader_dashboard.py"

# CORRECTED INDENTATION (8 spaces for body)
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
    # It looks like:
    #     def _update_delta_safe(self):
    #     try:
    
    # We will replace the whole method again, but be careful with regex matching the *bad* version.
    # The bad version has `try:` possibly indented with 4 spaces (same as def) or 0?
    # From the `cat -n` output, line 1434 and 1435 look aligned visually in the terminal output which pads line numbers.
    # But Python said `try:` was the error. 
    
    # Let's match based on function name header
    print("Replacing _update_delta_safe with corrected indentation...")
    content = re.sub(
        r"def _update_delta_safe\(self\):.*?(?=\n\s+def|\n\s+async def|\n\s+class|\nif __name__)", 
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
