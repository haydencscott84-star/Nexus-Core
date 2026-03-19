import json
import os
import shutil
import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_TO_REPAIR = ["nexus_sweeps_v1.json", "nexus_sweeps_v2.json"]

def repair_json(filename):
    filepath = os.path.join(SCRIPT_DIR, filename)
    if not os.path.exists(filepath):
        print(f"File not found: {filename}")
        return

    print(f"Repairing {filename}...")
    
    # Backup
    backup_path = filepath + ".bak"
    shutil.copy(filepath, backup_path)
    print(f"  -> Backup created at {backup_path}")

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Attempt to find the first valid JSON object
        # If "Extra data" is the issue, it usually means multiple JSON objects are concatenated.
        # We'll try to parse the string until we find a valid object.
        
        valid_data = None
        try:
             valid_data = json.loads(content)
             print("  -> File is already valid JSON.")
        except json.JSONDecodeError as e:
            print(f"  -> JSON Error: {e}")
            # Try to salvage up to the error position if "Extra data"
            if "Extra data" in str(e):
                # The error message format is usually "Extra data: line X column Y (char Z)"
                # We can try to assume the first object ends before char Z-ish.
                # A dumber but safer way: Count braces.
                pass
            
            # Smart salvage: Scan for balanced braces
            d = 0
            json_end = -1
            in_string = False
            escape = False
            
            for i, char in enumerate(content):
                if char == '"' and not escape:
                    in_string = not in_string
                if not in_string:
                    if char == '{': d += 1
                    elif char == '}': 
                        d -= 1
                        if d == 0:
                            json_end = i + 1
                            break
                            
                if char == '\\' and not escape: escape = True
                else: escape = False
            
            if json_end > 0:
                potential_json = content[:json_end]
                try:
                    valid_data = json.loads(potential_json)
                    print(f"  -> Salvaged valid JSON object (Length: {len(potential_json)} chars)")
                except:
                    print(f"  -> Salvage failed.")
            else:
                 print(f"  -> Could not find balanced JSON object.")

    except Exception as e:
        print(f"  -> Read/IO Error: {e}")

    # Write back
    if valid_data is not None:
        with open(filepath, 'w') as f:
            json.dump(valid_data, f, indent=2)
        print("  -> Write successful.")
    else:
        # Emergency Reset
        print("  -> CRITICAL: Could not salvage. Resetting to empty object.")
        with open(filepath, 'w') as f:
            json.dump({}, f)

if __name__ == "__main__":
    for f in FILES_TO_REPAIR:
        repair_json(f)
