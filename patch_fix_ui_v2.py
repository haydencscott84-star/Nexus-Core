
import re

DEBIT_FILE = "nexus_debit_downloaded.py"

def patch_ui_v2():
    with open(DEBIT_FILE, 'r') as f: content = f.read()

    # We need to find: yield Select.from_values(["CALL", "PUT"], allow_blank=False, value="CALL", id="type_select", classes="control-item")
    # And insert the Input after it.
    
    # Exact string from file download (line 154)
    target = 'yield Select.from_values(["CALL", "PUT"], allow_blank=False, value="CALL", id="type_select", classes="control-item")'
    injection = 'yield Select.from_values(["CALL", "PUT"], allow_blank=False, value="CALL", id="type_select", classes="control-item")\n            yield Input(placeholder="Strike", id="strike_input", classes="control-item")'
    
    if target in content and 'id="strike_input", classes="control-item")' not in content:
        content = content.replace(target, injection)
        print("Success: Inserted Strike Input into Compose.")
    elif 'id="strike_input", classes="control-item")' in content:
        print("Info: Strike Input already present.")
    else:
        print("Error: Could not find target line for injection.")
        
    with open(DEBIT_FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_ui_v2()
