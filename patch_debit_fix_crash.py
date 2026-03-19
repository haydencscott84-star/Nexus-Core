
import re

# PATCH V3: Fix SyntaxError & Missing Import
TARGET_FILE = "/root/nexus_debit.py"

def apply_fix():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # 1. FIX MISSING IMPORT
        if "import aiohttp" not in content:
            content = "import aiohttp\n" + content
            print("Import Added: aiohttp")

        # 2. FIX SYNTAX ERROR IN DEBUG BLOCK
        # The broken line likely looks messed up due to shell escaping of \n
        # We will look for the context and replace the whole block with something SAFE.
        
        # We search for the start of the loop
        start_marker = "for s in chain_data:"
        
        # We want to replace the FIRST few lines of the loop with valid code.
        # Clean Version:
        new_block = """            for s in chain_data:
                 # SAFE LOGGING
                 if s == chain_data[0]:
                     try:
                         with open('/root/debit_debug.txt', 'w') as df:
                             keys_str = str(list(s.keys()))
                             df.write("KEYS: " + keys_str + "\\n")
                             df.write(f"FULL: {s}")
                     except Exception as e:
                         pass"""

        # We need to find the messy block to replace it.
        # It starts with 'for s in chain_data:' and ends before 'ask_short ='
        
        regex = r'for s in chain_data:.+?ask_short ='
        
        # We construct the replacement to include the 'ask_short =' line so we don't lose it
        replacement = new_block + "\n                 ask_short ="
        
        if re.search(regex, content, re.DOTALL):
            content = re.sub(regex, replacement, content, count=1, flags=re.DOTALL)
            print("SUCCESS: Debug Block Repaired")
        else:
            print("ERROR: Could not locate broken debug block via regex.")
            # Fallback: The previous patch might have mangled it so bad regex doesn't match.
            # We try to find just the loop line and assume the next lines are the broken ones?
            # Risky. Let's try matching just the header of the if.
            
        with open(TARGET_FILE, 'w') as f:
            f.write(content)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_fix()
