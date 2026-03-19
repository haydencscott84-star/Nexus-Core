
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f:
        content = f.read()

    # We want to inject logging at the start of update_positions
    # def update_positions(self, positions):
    
    if "def update_positions(self, positions):" in content:
        # We replace the function signature with signature + logging
        new_content = content.replace(
            "def update_positions(self, positions):",
            "def update_positions(self, positions):\n        try:\n            with open('/root/pos_debug.log', 'w') as f: f.write(str(positions))\n        except: pass"
        )
        
        with open(path, 'w') as f:
            f.write(new_content)
        print("LOGGER_INJECTED")
    else:
        print("FUNCTION_NOT_FOUND")

except Exception as e:
    print(f"ERROR: {e}")
