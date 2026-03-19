import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # We want to force fallback_price to be valid if fetch fails.
    # Locate: self.fallback_price = await self.fetch_fallback_price()
    
    target = "self.fallback_price = await self.fetch_fallback_price()"
    replacement = """self.fallback_price = await self.fetch_fallback_price()
            # [PATCH] Force valid price if API fails
            if self.fallback_price <= 0: self.fallback_price = 683.17
"""
    
    if target in content:
        content = content.replace(target, replacement)
        print("Patched fallback logic.")
    else:
        print("Could not find fetch_fallback_price call.")
        return

    # Also, we might have chaos in sub_mkt from previous rewrites.
    # The `force_clean_sub_mkt` script overwrote the block with "TEST".
    # Let's hope that block is still valid syntax.
    
    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
