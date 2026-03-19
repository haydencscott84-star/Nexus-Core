import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Insert _update_delta_safe method before main execution
    # We look for 'if __name__ == "__main__":'
    if 'if __name__ == "__main__":' not in content:
        print("Could not find main execution block.")
        return

    new_method = """
    def _update_delta_safe(self):
        try:
            nd = self.calculate_net_delta()
            self.query_one('#m-delta', Metric).update_val(f'{nd:+.1f}', '#8fbcbb')
        except Exception as e:
            self.log_msg(f"[ERR] Delta Update: {e}")

"""
    # Insert before the main block
    content = content.replace('if __name__ == "__main__":', new_method + 'if __name__ == "__main__":')
    print("Inserted _update_delta_safe method.")

    # 2. Replace the messy block in sub_mkt
    # We look for the block we injected previously.
    # It starts with "# [PATCH] Force Initial Delta Update"
    # And ends before "while True:" usually, or just replace the inner try/except block.
    
    # Let's match the block aggressively.
    # Pattern:
    # # [PATCH] Force Initial Delta Update
    # ... (anything)
    # except Exception as e: self.log_msg(f"[ERR] Init Delta: {e}")
    
    # We will replace it with:
    # # [PATCH] Force Initial Delta Update
    # self._update_delta_safe()
    
    pattern = r"# \[PATCH\] Force Initial Delta Update.*?except Exception as e: self\.log_msg\(f\"\[ERR\] Init Delta: \{e\}\"\)"
    
    replacement = """# [PATCH] Force Initial Delta Update
                 self._update_delta_safe()"""
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    if new_content == content:
        print("Regex failed to find the block. Trying fallback cleanup.")
        # Fallback: Just look for the start marker and delete X lines?
        # Or look for line-by-line.
        lines = content.splitlines()
        final_lines = []
        skip = False
        
        for line in lines:
            if "# [PATCH] Force Initial Delta Update" in line:
                # We found the start.
                # We want to keep this line (or replace it with the new call)
                # Let's assume we want to put the call here and skip the old block.
                # The old block is:
                # [PATCH] ...
                # try:
                #    ...
                # except ...
                
                # We will output:
                #                 # [PATCH] Force Initial Delta Update
                #                 self._update_delta_safe()
                
                # Use the indentation of the found line
                indent = line[:line.find("#")]
                final_lines.append(indent + "# [PATCH] Force Initial Delta Update")
                final_lines.append(indent + "self._update_delta_safe()")
                skip = True
            elif skip and "except Exception as e:" in line and "Init Delta" in line:
                skip = False # Stop skipping after this line
            elif skip:
                # We are skipping the body of the bad block
                # Be careful not to skip too much if we miss the except line.
                # The except line we are looking for is: except Exception as e: self.log_msg(f"[ERR] Init Delta: {e}")
                pass
            else:
                final_lines.append(line)
        
        content = "\n".join(final_lines) + "\n"
        print("Fallback cleanup applied.")
    else:
        content = new_content
        print("Regex replacement successful.")

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
