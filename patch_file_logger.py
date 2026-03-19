
import re

# PATCH: File-Based Logger to debug Debit Data Keys
TARGET_FILE = "/root/nexus_debit.py"

def apply_file_logger():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # We look for the loop start again
        target = "for s in chain_data:"
        
        # New injection writes to FILE not self.log_msg
        injection = """
            for s in chain_data:
                 # FILE DEBUG
                 if s == chain_data[0]:
                     try:
                         with open('/root/debit_debug.txt', 'w') as df:
                             df.write(f"KEYS: {list(s.keys())}\\n")
                             df.write(f"FULL: {s}")
                     except: pass
"""
        
        # First, remove old injection if present
        # (Naive removal: just look for the distinct string we added before)
        content = content.replace('self.log_msg(f"DEBUG KEYS: {list(s.keys())}")', 'pass # OLD LOG')
        
        # Now apply new one
        if target in content and "debit_debug.txt" not in content:
            # We replace 'for s in chain_data:' with the injection
            # But we need to match broadly because we already modified it?
            # Actually, my previous verify showed the 'for s in chain_data:' line is clean above the injection?
            # No, the previous `sed` showed:
            # for s in chain_data:
            #      # DEBUG: Log keys...
            
            # So I should look for the DEBUG comment I added
            debug_marker = "# DEBUG: Log keys for first item"
            if debug_marker in content:
                # Replace the whole block I added previously
                # I'll just use regex to swap the inside of the if
                print("Found old logger, upgrading to file logger...")
                content = content.replace('self.log_msg(f"DEBUG KEYS: {list(s.keys())}")', 
                                          "with open('/root/debit_debug.txt', 'w') as df: df.write(f'FULL: {s}')")
            else:
                # Fresh injection
                content = content.replace(target, injection.strip())
            
            with open(TARGET_FILE, 'w') as f:
                f.write(content)
            print("SUCCESS: File Logger Injected")
            
        else:
            print("Logger already present or target not found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_file_logger()
