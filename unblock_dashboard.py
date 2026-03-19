import re
import pandas as pd

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # We want to replace valid await call with non-blocking task + init
    # Pattern: match `await self.fetch_orats_greeks()`
    
    # We also want to make sure we init the dataframe BEFORE the task.
    
    replacement = """
        # [PATCH] Unblocking ORATS fetch 
        self.orats_chain = pd.DataFrame()
        asyncio.create_task(self.fetch_orats_greeks())
"""
    
    # Use simple string replace if exact match found
    if "await self.fetch_orats_greeks()" in content:
        content = content.replace("await self.fetch_orats_greeks()", replacement.strip())
        print("Replaced await call with background task.")
    else:
        print("Could not find 'await self.fetch_orats_greeks()'. It might have been modified already.")
        # Fallback regex?
        # re.sub(r"await\s+self\.fetch_orats_greeks\(\)", ...)
    
    # Also ensuring pandas is imported if not? 
    # Usually it is. We won't touch imports to avoid risk.

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
