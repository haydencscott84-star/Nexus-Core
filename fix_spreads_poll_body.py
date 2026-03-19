
TARGET_FILE = "/root/nexus_spreads.py"

def fix_poll_body():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        in_poll_method = False
        
        for line in lines:
            stripped = line.strip()
            
            # Detect method start
            if "async def poll_orats_greeks(self):" in line:
                in_poll_method = True
                # Ensure def is at 4 spaces
                new_lines.append("    async def poll_orats_greeks(self):\n")
                continue
            
            # Detect end of method (next method start)
            if in_poll_method and "def populate_chain" in line:
                in_poll_method = False
            
            if in_poll_method:
                # This is body content. Should be at 8 spaces (or more).
                if not stripped: # Empty line
                    new_lines.append(line)
                else:
                    # Check current indent
                    current_indent = len(line) - len(line.lstrip())
                    
                    # If it's 4 spaces (same as def), push to 8.
                    if current_indent == 4:
                        new_lines.append("    " + line)
                    elif current_indent < 8:
                        # Force to 8
                         new_lines.append("        " + line.lstrip())
                    else:
                        # Already indented enough? Keep as is or re-align?
                        # Better to keep relative indent.
                        # If existing is 8, keep 8.
                        new_lines.append(line)
            else:
                new_lines.append(line)

        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Poll Body Indent Fixed.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_poll_body()
