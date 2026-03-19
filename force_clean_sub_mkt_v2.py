import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # We want to replace the block starting at "[PATCH] Force Initial Delta Update"
    # and ending at the except line.
    
    # We'll use a Pattern that captures the MESSY INTERNALS.
    # Start: "# [PATCH] Force Initial Delta Update"
    # End: "except Exception as e: self.log_msg"
    
    # We need to be careful with regex dots matching newlines.
    
    pattern = r"(# \[PATCH\] Force Initial Delta Update\n\s+try:\n.*?except Exception as e: self\.log_msg\(f\"\[ERR\] Init Delta: \{e\}\"\))"
    
    # Construct the CLEAN replacement
    base_indent = "                 " # 17 spaces
    inner_indent = base_indent + "    " # 21 spaces
    
    replacement = f"""# [PATCH] Force Initial Delta Update
{base_indent}try:
{inner_indent}nd_init = self.calculate_net_delta()
{inner_indent}self.log_msg(f"[DEBUG] Init Delta: {{nd_init}}")
{inner_indent}self.query_one('#m-delta', Metric).update_val(f'{{nd_init:+.1f}}', '#8fbcbb')
{base_indent}except Exception as e: self.log_msg(f"[ERR] Init Delta: {{e}}")"""
    
    # Perform substitution
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    if new_content != content:
        print("Replaced messy block.")
        print("Writing fixed file...")
        with open(TARGET_FILE, 'w') as f:
            f.write(new_content)
        print("Success.")
    else:
        print("Could not find block pattern. Using rigid line replacement.")
        # Fallback: Read lines and replace manually
        # This is safer if regex fails due to whitespace complexity
        lines = content.splitlines()
        final_lines = []
        skip = False
        
        for line in lines:
            if "# [PATCH] Force Initial Delta Update" in line:
                final_lines.append(base_indent + "# [PATCH] Force Initial Delta Update")
                final_lines.append(base_indent + "try:")
                final_lines.append(inner_indent + "nd_init = self.calculate_net_delta()")
                final_lines.append(inner_indent + 'self.log_msg(f"[DEBUG] Init Delta: {nd_init}")')
                final_lines.append(inner_indent + "self.query_one('#m-delta', Metric).update_val(f'{nd_init:+.1f}', '#8fbcbb')")
                final_lines.append(base_indent + 'except Exception as e: self.log_msg(f"[ERR] Init Delta: {e}")')
                skip = True
            elif skip and "except Exception as e:" in line:
                skip = False
                continue # The line was already added
            elif skip and "nd_init =" in line:
                continue
            elif skip and "self.log_msg" in line:
                continue
            elif skip and "self.query_one" in line:
                continue
            elif skip and "try:" in line:
                continue
            elif skip:
                # If we hit a line that doesn't look like part of the block (e.g. while True), stop skipping
                if "while True:" in line:
                     skip = False
                     final_lines.append(line)
            else:
                final_lines.append(line)
        
        with open(TARGET_FILE, 'w') as f:
            f.write("\n".join(final_lines) + "\n")
        print("Success (Lines Replaced).")

if __name__ == "__main__":
    apply_fix()
