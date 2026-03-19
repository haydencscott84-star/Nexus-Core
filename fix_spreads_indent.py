
TARGET_FILE = "/root/nexus_spreads.py"

def fix_indentation():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        inside_poll = False
        
        for line in lines:
            stripped = line.strip()
            
            # Detect start of our problematic function
            if "async def poll_orats_greeks(self):" in line:
                inside_poll = True
                new_lines.append(line) # Keep def line as is
                continue
            
            # Detect end of function (Start of next function)
            if inside_poll and ("def calculate_true_win_rate" in line or "def populate_chain" in line):
                inside_poll = False
            
            if inside_poll:
                # If content exists (not empty line), add 4 extra spaces
                if stripped:
                    # We want to indent everything inside the function body
                    # The current lines seem to be at 8 spaces (same as def)
                    # We want them at 12 spaces.
                    # Or simply: if it starts with 8 spaces and is NOT the def, add 4.
                    
                    # Safer approach: Just verify if it's the body lines we injected
                    if line.startswith("        while True:") or line.startswith("            try:") or line.startswith("                url =") or line.startswith("                params =") or line.startswith("                async with") or line.startswith("                        if r.status") or line.startswith("                            data =") or line.startswith("                            temp_map") or line.startswith("                            for i") or line.startswith("                                try:") or line.startswith("                                    k =") or line.startswith("                                    d =") or line.startswith("                                    v =") or line.startswith("                                    temp_map[k]") or line.startswith("                                except:") or line.startswith("                            if temp_map"):
                         new_lines.append("    " + line)
                    elif line.startswith("            except"):
                         new_lines.append("    " + line)
                    elif line.startswith("                 # self.log"): # commented out log
                         new_lines.append("    " + line)
                    elif line.startswith("                 pass"):
                         new_lines.append("    " + line)
                    elif line.startswith("            await"):
                         new_lines.append("    " + line)
                    else:
                        # Fallback for empty lines or weirdly formatted ones
                        new_lines.append(line)
                else:
                    new_lines.append(line) # Empty lines
            else:
                new_lines.append(line)
        
        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Indentation fixed.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_indentation()
