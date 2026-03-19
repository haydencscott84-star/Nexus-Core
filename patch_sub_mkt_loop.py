import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    print("Replacing old manual delta update in sub_mkt with _update_delta_safe call...")
    
    # We look for the specific lines seen in `cat`
    #   nd = self.calculate_net_delta()
    #   self.query_one("#m-delta", Metric).update_val(f"{nd:+.1f}", "#8fbcbb")
    
    # Regex needs to be flexible with whitespace
    # Pattern: \s+nd = self\.calculate_net_delta\(\)\s+self\.query_one.*?update_val.*?
    
    pattern = r"nd = self\.calculate_net_delta\(\)\s+self\.query_one\(\"#m-delta\", Metric\)\.update_val\(f\"{nd:\+\.1f}\", \"#8fbcbb\"\)"
    
    # Replacement
    replacement = "self._update_delta_safe()"
    
    new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    
    if new_content == content:
        print("Regex didn't match. Trying simpler string replace...")
        # Exact string match based on `cat` output (assuming standard indentation/newlines)
        # 629:                              nd = self.calculate_net_delta()
        # 630:                              self.query_one("#m-delta", Metric).update_val(f"{nd:+.1f}", "#8fbcbb")
        
        # We'll search for the specific lines.
        old_block = 'nd = self.calculate_net_delta()\n                            self.query_one("#m-delta", Metric).update_val(f"{nd:+.1f}", "#8fbcbb")'
        if old_block in content:
            new_content = content.replace(old_block, 'self._update_delta_safe()')
            print("String replace worked.")
        else:
            print("String replace failed too. Check source.")

    with open(TARGET_FILE, 'w') as f:
        f.write(new_content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
