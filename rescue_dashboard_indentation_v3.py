import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        lines = f.readlines()

    new_lines = []
    
    reference_indent = "                 " # Default 17 spaces
    
    for i, line in enumerate(lines):
        # Capture valid indentation from nearby line
        if "und_price = self.fallback_price" in line:
            reference_indent = line[:line.find("self.query_one")]
            new_lines.append(line)
            continue

        stripped = line.strip()
        
        # Identify the block lines by content signatures
        if stripped.startswith("try:") and "nd_init =" in lines[i+1]:
            # The try line
            print(f"Fixing 'try:' at {i+1}")
            new_lines.append(reference_indent + "try:\n")
            
        elif stripped.startswith("nd_init ="):
            # Inside try
            new_lines.append(reference_indent + "    " + stripped + "\n")
            
        elif stripped.startswith('self.log_msg(f"[DEBUG]'):
            new_lines.append(reference_indent + "    " + stripped + "\n")
            
        elif stripped.startswith("self.query_one('#m-delta'"):
            new_lines.append(reference_indent + "    " + stripped + "\n")
            
        elif stripped.startswith("except Exception as e:") and "[ERR] Init Delta" in stripped:
             # The Except line
            print(f"Fixing 'except:' at {i+1}")
            new_lines.append(reference_indent + stripped + "\n") # Match try level
            
        else:
            new_lines.append(line)

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.writelines(new_lines)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
