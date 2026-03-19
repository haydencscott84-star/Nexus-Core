import re

TARGET_FILE = "/root/trader_dashboard.py"

# The clean method we want
CLEAN_METHOD = """
    def _update_delta_safe(self):
        try:
            nd, ng = self.calculate_net_delta()
            # Format: "DELTA: +315 | Γ: -15"
            g_color = "#bf616a" if ng < 0 else "#a3be8c"
            
            label = f"{nd:+.0f} | Γ {ng:+.0f}"
            try:
                self.query_one('#m-delta', Metric).update_val(label, g_color)
            except: pass
            
        except Exception as e:
            self.log_msg(f"[ERR] Delta Update: {e}")

    async def fetch_orats_greeks(self):"""

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # Regex to find the span from 'CANCEL ERR' down to 'fetch_orats_greeks'
    # We want to replace everything in between with the CLEAN_METHOD
    
    # Start anchor: `CANCEL ERR: {e}")`
    # End anchor: `def fetch_orats_greeks(self):` (we include current declaration in replacement to be safe)
    # The mess includes multiple `def _update...` and try/except blocks.
    
    print("Replacing duplicated/messy code block...")
    
    pattern = r'(CANCEL ERR: \{e\}"\)).*?async def fetch_orats_greeks\(self\):'
    
    # Check if match exists
    match = re.search(pattern, content, flags=re.DOTALL)
    if match:
        print("Match found!")
        # Replace keeping the first group (the CANCEL ERR line end)
        new_content = re.sub(pattern, r'\1' + CLEAN_METHOD, content, flags=re.DOTALL)
        
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
        print("Success.")
    else:
        print("Pattern not found. Dumping snippet for debug:")
        # Dump 1000 chars around the area
        idx = content.find('CANCEL ERR')
        if idx != -1:
            print(content[idx:idx+500])
        else:
            print("Could not find anchor 'CANCEL ERR'")

if __name__ == "__main__":
    apply_fix()
