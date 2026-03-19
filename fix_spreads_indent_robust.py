
TARGET_FILE = "/root/nexus_spreads.py"

def fix_indentation():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        target_methods = ["def calculate_pop", "def populate_chain"]
        inside_target = False
        
        for line in lines:
            stripped = line.strip()
            
            # Check for start of target method
            is_start = False
            for tm in target_methods:
                if tm in line:
                    inside_target = True
                    is_start = True
                    break
            
            if is_start:
                new_lines.append(line)
                continue
            
            # Check for end of target method (start of next one)
            if inside_target:
                 if line.startswith("    def ") or line.startswith("    async def "):
                     inside_target = False
            
            if inside_target:
                # If content exists and is not empty, indent it 4 spaces deeper
                # Assuming the current state is 8 spaces (same as def)
                if stripped:
                     # Heuristic: if it looks like body code, add 4 spaces
                     if line.startswith("        ") and not line.startswith("            "):
                          new_lines.append("    " + line)
                     else:
                          new_lines.append(line)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Robust Indentation Fix Applied.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_indentation()
