import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # We want to move `self._update_delta_safe()` OUT of the `if not is_sleep_mode():` block.
    # Currently:
    #     if not is_sleep_mode():
    #         ...
    #         # [PATCH] Force Initial Delta Update
    #         self._update_delta_safe()
    
    # We will simply prepend it to the start of sub_mkt? 
    # Or just insert it before `if not is_sleep_mode():`
    
    # Let's find `if not is_sleep_mode():` inside `sub_mkt`.
    # And insert `self._update_delta_safe()` before it.
    
    # Also, remove the old call inside.
    
    # 1. Remove old call
    content = content.replace("self._update_delta_safe()", "")
    # Note: this removes ALL calls. Make sure there aren't others. 
    # There shouldn't be others except the one I added.
    
    # 2. Insert at start of sub_mkt
    # Look for: s.subscribe(b"SPY")
    
    tgt = 's.subscribe(b"SPY")'
    if tgt in content:
        # Insert after this line
        rep = f'{tgt}\n        self._update_delta_safe() # Force Init'
        content = content.replace(tgt, rep)
        print("Moved _update_delta_safe to start of sub_mkt.")
    else:
        print("Could not find s.subscribe(b'SPY')")
        return

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
