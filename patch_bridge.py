with open("nexus_sheets_bridge.py", "r") as f:
    content = f.read()

# I want to add a trigger at 16:32 to allow the 16:30 job 2 minutes to finish uploading
# the raw historic data before the pandas script parses it stringently.

target_block = """            elif cur_time == "16:30":
                 try: run_orats_oi_dump()
                 except Exception as e: print(f"❌ ORATS OI DUMP ERROR: {e}")"""

replacement = """            elif cur_time == "16:30":
                 try: run_orats_oi_dump()
                 except Exception as e: print(f"❌ ORATS OI DUMP ERROR: {e}")
                 
            # Note: Run the 5-Day Ledger analysis at 16:35 specifically to give the
            # ORATS snapshot script above 5 minutes to finish its Google Sheet uploads
            elif cur_time == "16:35":
                 try:
                     import subprocess
                     print("🔥 TRIGGERING 5-DAY FLOW LEDGER PANDAS CALCULATION (16:35)")
                     subprocess.run(["python3", "/root/update_ledger_sheet.py"], check=True)
                 except Exception as e:
                     print(f"❌ FLOW LEDGER ERROR: {e}")"""

if target_block in content:
    with open("nexus_sheets_bridge.py", "w") as f:
        f.write(content.replace(target_block, replacement))
    print("Bridge Patched!")
else:
    print("Could not find exact block to replace.")
