
TARGET_FILE = "/root/nexus_debit.py"

def apply_patch():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # 1. Update on_mount columns
        old_cols = '"EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "MAX PROFIT", "RETURN %", "L. DELTA"'
        new_cols = '"EXPIRY", "DTE", "LONG (ITM)", "SHORT (OTM)", "DEBIT", "% TO B/E", "PROB. ADJ.", "MAX ROC %", "B/E", "WIN %"'
        
        if old_cols in content:
            content = content.replace(old_cols, new_cols)
            print("Headers updated in on_mount.")
        else:
            print("Could not find old headers in on_mount.")

        # 2. Add DEBUG log to populate_debit_chain
        # Locate the function start and inject log
        marker = 'def populate_debit_chain(self, chain_data, width, target_strike=0.0, ivr=0.0):'
        if marker in content:
            # We want to inject logging right after try:
            # Current structure:
            # def ...
            #     try:
            #         table = ...
            
            # We will replace 'try:' with 'try:\n            self.log_msg("DEBUG: Populate Called")'
            # Be careful with replacements if 'try:' appears multiple times.
            # We can use the marker + try context.
            
            chunk_old = f"""{marker}
        try:"""
            chunk_new = f"""{marker}
        try:
            self.log_msg("DEBUG: Populate Called")"""
            
            if chunk_old in content:
                content = content.replace(chunk_old, chunk_new)
                print("Debug log injected.")
            else:
                 print("Could not match populate_debit_chain context for logging.")
        
        with open(TARGET_FILE, 'w') as f:
            f.write(content)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_patch()
