import re
import os
import sys

TARGET_FILE = "/root/trader_dashboard.py"

def apply_patch():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Update Header Widget Layout
    # Find the line constructing the metrics
    old_metrics = 'for x in ["ACCT","SIG","EXP","PL","SPY"]'
    new_metrics = 'for x in ["ACCT","SIG","EXP","PL","SPY","DELTA"]'
    
    if old_metrics in content and new_metrics not in content:
        print("Patching Header Metrics...")
        content = content.replace(old_metrics, new_metrics)
    else:
        print("Header Metrics already patched or not found.")

    # 2. Inject `calculate_net_delta` and `fetch_initial_greeks`
    if "def calculate_net_delta(self):" not in content:
        print("Injecting calculate_net_delta...")
        method_logic = """
    def calculate_net_delta(self):
        net_delta = 0.0
        try:
            curr_spy = getattr(self.query_one(ExecutionPanel), 'und_price', 0.0)
            if curr_spy <= 0: return 0.0
            
            for sym, pos in self.pos_map.items():
                qty = float(pos.get('qty', 0))
                if qty == 0: continue
                
                # Fetch Greeks on Entry (One-time)
                if 'entry_delta' not in pos:
                    # Mark as fetching to avoid spam
                    pos['entry_delta'] = 0.0
                    pos['entry_gamma'] = 0.0
                    pos['entry_spot'] = curr_spy 
                    self.run_worker(self.fetch_initial_greeks(sym))
                
                e_delta = pos.get('entry_delta', 0.0)
                e_gamma = pos.get('entry_gamma', 0.0)
                e_spot = pos.get('entry_spot', curr_spy)
                
                # Dynamic Calculation: D_new = D_old + Gamma * (Price_new - Price_old)
                price_diff = curr_spy - e_spot
                curr_delta = e_delta + (e_gamma * price_diff)
                
                # Multiplier 100 for options
                net_delta += (qty * 100 * curr_delta)
                
        except Exception as e:
            return 0.0
        return net_delta

    async def fetch_initial_greeks(self, sym):
        try:
            # Attempt to fetch via internal client if available, or just ignore
            # This is a placeholder that eventually needs to connect to pypiex/tda
            # For now we rely on 0.0 or if valid greeks are in pos_map already
            pass
        except: pass
"""
        # Insert before `def watch_price`
        content = content.replace("def watch_price(self, val):", method_logic + "\n    def watch_price(self, val):")

    # 3. Hook the Update Loop (sub_mkt)
    # Target: self.query_one("#m-spy", Metric).update_val(f"${p:.2f}", "#ebcb8b")
    # We want to add the delta update right after.
    
    hook_target = 'self.query_one("#m-spy", Metric).update_val(f"${p:.2f}", "#ebcb8b")'
    hook_payload = """self.query_one("#m-spy", Metric).update_val(f"${p:.2f}", "#ebcb8b")
                            # [PATCH] Update Delta
                            nd = self.calculate_net_delta()
                            self.query_one("#m-delta", Metric).update_val(f"{nd:+.1f}", "#8fbcbb")"""
    
    if hook_target in content and "#m-delta" not in content:
        print("Hooking Update Loop...")
        content = content.replace(hook_target, hook_payload)
    else:
         print("Update Loop already hooked or target not found.")

    print("Writing patched file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_patch()
