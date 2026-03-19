
import os
import sys

target_file = "/root/alert_manager.py"
print(f"Applying Weekend Silence Patch to {target_file}...")

# Logic:
# Check if today is Saturday (5) or Sunday (6).
# If so, return immediately.

patch_code = """    # [Weekend Silence] Block alerts on Sat/Sun
    import datetime
    if datetime.datetime.today().weekday() >= 5:
        if DEBUG_MODE: console.print("[dim][Weekend] Alert silenced.[/]")
        return
"""

try:
    with open(target_file, 'r') as f:
        lines = f.readlines()

    new_lines = []
    patched = False
    
    for line in lines:
        new_lines.append(line)
        # Look for the function definition
        if "def send_discord_alert(title, description, color):" in line and not patched:
            print("Found target function. Injecting silence logic...")
            new_lines.append(patch_code)
            patched = True
            
    if patched:
        with open(target_file, 'w') as f:
            f.writelines(new_lines)
        print("Success! Weekend silence logic injected.")
    else:
        print("Error: Could not find function definition.")

except Exception as e:
    print(f"Patch Error: {e}")
