import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # Regex to find `async def fetch_orats_greeks` and ensure it has 4 spaces.
    # It might have arbitrary spaces before it due to previous edits.
    print("Normalizing indentation for fetch_orats_greeks...")
    
    # \s+ matches any whitespace (including newlines? no, excluding).
    # We want to replace `[any_indent]async def fetch_orats_greeks` with `    async def fetch_orats_greeks`
    
    # We use multiline mode or just search for the specific signature
    content = re.sub(r"^\s+async def fetch_orats_greeks\(self\):", "    async def fetch_orats_greeks(self):", content, flags=re.MULTILINE)

    print("Writing file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
