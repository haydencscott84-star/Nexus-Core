
import re

# DEBUG SCRIPT: Inject Raw Data Logging to find correct Delta Key
TARGET_FILE = "/root/nexus_debit.py"

def inject_logger():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # Target the start of the loop
        target = "for s in chain_data:"
        
        # We inject a log_msg for the first item only
        injection = """
            for s in chain_data:
                 # DEBUG: Log keys for first item
                 if s == chain_data[0]:
                     try:
                         self.log_msg(f"DEBUG KEYS: {list(s.keys())}")
                         if 'greeks' in s: self.log_msg(f"DEBUG GREEKS: {s['greeks']}")
                         if 'long_leg' in s: self.log_msg(f"DEBUG LONG: {s['long_leg']}")
                     except: pass
"""
        if target in content and "DEBUG KEYS" not in content:
            content = content.replace(target, injection.strip())
            print("SUCCESS: Logger Injected")
            
            with open(TARGET_FILE, 'w') as f:
                f.write(content)
        else:
            print("Logger already present or target not found.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    inject_logger()
