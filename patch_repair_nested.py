
# PATCH REPAIR NESTED
# Fixes get_k indentation which was flattened by force_indent.

FILE = "nexus_debit_downloaded.py"

def repair():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.strip().startswith("def get_k(s):"):
            # Should be 8 spaces (nested in update_positions or similar)
            # Previously it was forced to 4 spaces: "    def get_k(s):\n"
            # We want "        def get_k(s):\n"
            new_lines.append("        def get_k(s):\n")
            print("Restored get_k indentation to 8 spaces.")
        else:
            new_lines.append(line)
            
    with open(FILE, 'w') as f: f.writelines(new_lines)

if __name__ == "__main__":
    repair()
