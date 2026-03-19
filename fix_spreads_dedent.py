
TARGET_FILE = "/root/nexus_spreads.py"

def fix_dedent():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        in_poll_method = False
        dedent_amount = 0
        
        for i, line in enumerate(lines):
            # Check for start of poll method
            if "async def poll_orats_greeks(self):" in line:
                current_indent = len(line) - len(line.lstrip())
                target_indent = 4
                dedent_amount = current_indent - target_indent
                
                if dedent_amount > 0:
                    in_poll_method = True
                    print(f"Aligning poll_orats_greeks from {current_indent} to {target_indent} spaces (Shift: {dedent_amount})")
                    new_lines.append(line[dedent_amount:])
                    continue
                else:
                     print("poll_orats_greeks seems already correct?")
                     new_lines.append(line)
                     continue
            
            # Check for end of poll method (start of next method)
            if in_poll_method and "def populate_chain" in line:
                in_poll_method = False
            
            if in_poll_method:
                # Dedent content
                if line.strip(): # if not empty
                    # Ensure we don't strip too much if it's a weird line, but mostly safe
                    if len(line.rstrip()) > dedent_amount:
                         new_lines.append(line[dedent_amount:])
                    else:
                         new_lines.append(line.lstrip()) # Fallback
                else:
                    new_lines.append(line) # preserve empty lines
            else:
                new_lines.append(line)

        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Dedent Fix Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_dedent()
