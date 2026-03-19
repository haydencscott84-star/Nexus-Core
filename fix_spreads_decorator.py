
TARGET_FILE = "/root/nexus_spreads.py"

def fix_decorator():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            # Fix specific incorrectly unindented decorator
            if line.startswith('@on(Input.Changed, "#qty_input")'):
                new_lines.append("    " + line)
            elif line.startswith('@on(DataTable.RowSelected'):
                 # Check just in case
                 new_lines.append("    " + line)
            else:
                new_lines.append(line)

        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Decorator Fix Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_decorator()
