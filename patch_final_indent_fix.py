
# PATCH FINAL INDENT FIX
# Indents the @on decorator for on_fetch

FILE = "nexus_debit_downloaded.py"

def fix_indent():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    new_lines = []
    for line in lines:
        if line.startswith('@on(Button.Pressed, "#fetch_btn")'):
            # It should be indented 4 spaces
            new_lines.append("    " + line)
            print("Indented @on decorator.")
        else:
            new_lines.append(line)
            
    with open(FILE, 'w') as f: f.writelines(new_lines)

if __name__ == "__main__":
    fix_indent()
