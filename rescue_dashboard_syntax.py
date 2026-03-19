import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        lines = f.readlines()

    new_lines = []
    fixed = False
    
    # Target line: begins with "; self.query_one" (stripped) or likely unindented
    # In the `cat -n` output, it was line 1040.
    
    for i, line in enumerate(lines):
        # Check for the broken line
        if line.strip().startswith('; self.query_one("#m-exp"'):
            print(f"Found broken line at {i+1}: {line.strip()}")
            
            # We need to indent it to match the 'try' block.
            # Looking at previous lines (e.g., line 1036 'try:')
            # Let's assume standard indentation of 16 spaces based on context
            # "                self.query_one..."
            
            # Remove leading "; "
            clean_line = line.strip()[2:] # Skip "; "
            
            # Add indentation
            indent = "                " # 16 spaces
            new_lines.append(indent + clean_line + "\n")
            fixed = True
        else:
            new_lines.append(line)

    if fixed:
        print("Writing fixed file...")
        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
        print("Success.")
    else:
        print("Could not find broken line. Check format.")

if __name__ == "__main__":
    apply_fix()
