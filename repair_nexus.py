
# Repair Script
DEBIT = "nexus_debit_downloaded.py"
SPREADS = "nexus_spreads_downloaded.py"

def repair_spreads():
    with open(SPREADS, 'r') as f: lines = f.readlines()
    
    # Locate End of Manager Loop
    end_mgr_idx = -1
    for i, line in enumerate(lines):
        if "await asyncio.sleep(5) # Pause to allow close to process" in line:
            end_mgr_idx = i
            break
            
    if end_mgr_idx == -1:
        print("Could not find End of Manager Loop")
        return

    # Locate Start of Real Active Quote Loop (Body)
    start_quote_body_idx = -1
    for i, line in enumerate(lines):
        if i > end_mgr_idx and "while True:" in line:
            # Check previous line for signature
            if "async def active_quote_loop(self):" in lines[i-1]:
                start_quote_body_idx = i - 1 # Signature
                break

    if start_quote_body_idx == -1:
        print("Could not find Start of Active Quote Loop")
        return

    print(f"Garbage from Line {end_mgr_idx+2} to {start_quote_body_idx}") 
    # +2 because end_mgr_idx is the sleep line. Next line might be blank or garbage.
    
    # Slices:
    # 0 to end_mgr_idx + 1 (keep sleep logic)
    # start_quote_body_idx to End (keep quote loop)
    # Insert blank line in between.
    
    new_lines = lines[:end_mgr_idx+1] + ["\n"] + lines[start_quote_body_idx:]
    
    with open(SPREADS, 'w') as f: f.writelines(new_lines)
    print("Repaired nexus_spreads.")

def verify_debit_zmq():
    with open(DEBIT, 'r') as f: content = f.read()
    if "import zmq.asyncio" in content and "transient" in content.lower():
        print("Nexus Debit ZMQ Patch Verified.")
    else:
        print("Nexus Debit ZMQ Patch MISSING.")

if __name__ == "__main__":
    repair_spreads()
    verify_debit_zmq()
