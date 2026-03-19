
import sys

path = '/root/nexus_spreads.py'
try:
    with open(path, 'r') as f:
        content = f.read()

    # We replace the function signature with signature + print
    if "def update_positions(self, positions):" in content:
        new_content = content.replace(
            "def update_positions(self, positions):",
            "def update_positions(self, positions):\n        print(f'DEBUG_POSITIONS: {positions}')\n"
        )
        # Also remove the previous file injection if it exists to clean up
        new_content = new_content.replace(
            "try:\n            with open('/root/pos_debug.log', 'w') as f: f.write(str(positions))\n        except: pass", 
            ""
        )
        
        with open(path, 'w') as f:
            f.write(new_content)
        print("LOGGER_PRINT_INJECTED")
    else:
        print("FUNCTION_NOT_FOUND")

except Exception as e:
    print(f"ERROR: {e}")
