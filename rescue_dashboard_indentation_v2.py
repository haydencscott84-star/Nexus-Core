import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        lines = f.readlines()

    new_lines = []
    
    # We look for the broken 'try:' block around line 655
    # The context is:
    # 651:                  self.query_one(ExecutionPanel).und_price = self.fallback_price
    # 653:                  # [PATCH] Force Initial Delta Update
    # 655: try:
    
    # We want to match the indentation of line 651 (or whichever line has 'und_price = self.fallback_price')
    
    reference_indent = "                 " # fallback
    
    for i, line in enumerate(lines):
        if "und_price = self.fallback_price" in line:
            # Capture the indentation
            reference_indent = line[:line.find("self.query_one")]
            new_lines.append(line)
        elif line.startswith("try:") and "nd_init =" in lines[i+1]:
            # This is the broken line!
            print(f"Found broken try at line {i+1}")
            new_lines.append(reference_indent + line)
        elif line.startswith("except Exception as e:") and "[ERR] Init Delta" in line:
             # This is the broken except line!
            print(f"Found broken except at line {i+1}")
            new_lines.append(reference_indent + line)
        elif "nd_init = self.calculate_net_delta()" in line:
            # Check inner indentation
            # It should be reference + 4 spaces
            stripped = line.strip()
            new_lines.append(reference_indent + "    " + stripped + "\n")
        elif 'self.log_msg(f"[DEBUG] Init Delta' in line:
            stripped = line.strip()
            new_lines.append(reference_indent + "    " + stripped + "\n")
        elif "self.query_one('#m-delta', Metric).update_val" in line:
            stripped = line.strip()
            new_lines.append(reference_indent + "    " + stripped + "\n")
        else:
            new_lines.append(line)

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.writelines(new_lines)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
