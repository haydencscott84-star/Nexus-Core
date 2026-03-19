
import re

# PATCH V2: Aggressive File Logger Replacement
TARGET_FILE = "/root/nexus_debit.py"

def apply_file_logger_v2():
    try:
        with open(TARGET_FILE, 'r') as f:
            content = f.read()

        # We look for the broken debug block
        # It currently looks like:
        # if s == chain_data[0]:
        #     try:
        #         pass # OLD LOG
        #         if 'greeks' in s: ...
        
        # We will match the start of the block and replace heavily
        
        start_marker = "if s == chain_data[0]:"
        end_marker = "except: pass"
        
        new_block = """                if s == chain_data[0]:
                    try:
                        with open('/root/debit_debug.txt', 'w') as df:
                            df.write(f"KEYS: {list(s.keys())}\\n")
                            df.write(f"FULL: {s}")
                    except Exception as e:
                        self.log_msg(f"File log error: {e}")"""

        # Regex to find the block roughly
        # We assume indentation is standard 4 spaces or similar
        regex = r'if s == chain_data\[0\]:.*?except: pass'
        
        if re.search(regex, content, re.DOTALL):
            content = re.sub(regex, new_block.strip(), content, flags=re.DOTALL)
            print("SUCCESS: Debug Block Replaced with File Logger")
            
            with open(TARGET_FILE, 'w') as f:
                f.write(content)
        else:
            print("Target debug block NOT FOUND for regex replacement.")
            # Fallback: simple string find/replace of the first line if regex fails due to spacing
            if start_marker in content:
                print("Using naive check...")
                # This is risky without knowing exact end, so we rely on regex mostly.
                # Let's try to match the exact content seen in the previous `cat`
                exact_chunk = """if s == chain_data[0]:
                     try:
                         pass # OLD LOG
                         if 'greeks' in s: self.log_msg(f"DEBUG GREEKS: {s['greeks']}")
                         if 'long_leg' in s: self.log_msg(f"DEBUG LONG: {s['long_leg']}")
                     except: pass"""
                # String replace might fail due to whitespace.
                # We will stick to the regex but make it whitespace flexible
                regex_flex = r'if\s+s\s*==\s*chain_data\[0\]:.*?except:\s*pass'
                content = re.sub(regex_flex, new_block.strip(), content, flags=re.DOTALL)
                with open(TARGET_FILE, 'w') as f:
                    f.write(content)
                print("SUCCESS: Debug Block Replaced (Flexible Regex)")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    apply_file_logger_v2()
