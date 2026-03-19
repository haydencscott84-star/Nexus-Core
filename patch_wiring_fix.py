
# PATCH WIRING FIX
# Adds @on decorator to on_fetch

FILE = "nexus_debit_downloaded.py"

def fix_wiring():
    with open(FILE, 'r') as f: content = f.read()
    
    if "async def on_fetch(self):" in content:
        # Check if already decorated
        if "@on(Button.Pressed, \"#fetch_btn\")" in content:
            print("Already wired.")
            return

        # Replace signature with decorated signature
        new_sig = '    @on(Button.Pressed, "#fetch_btn")\n    async def on_fetch(self):'
        content = content.replace('    async def on_fetch(self):', new_sig)
        
        with open(FILE, 'w') as f: f.write(content)
        print("Wired #fetch_btn to on_fetch.")
    else:
        print("on_fetch method not found.")

if __name__ == "__main__":
    fix_wiring()
