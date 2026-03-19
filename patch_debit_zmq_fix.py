
# PATCH DEBIT ZMQ FIX
# Target: nexus_debit_downloaded.py
# Problem: Background loop contends with Manual Scan for REQ socket.
# Solution: Disable fetch_managed_spreads_loop (Redundant).

FILE = "nexus_debit_downloaded.py"

OLD_LINE = 'self.run_worker(self.fetch_managed_spreads_loop)'
NEW_LINE = '# self.run_worker(self.fetch_managed_spreads_loop) # DISABLED (ZMQ CONTENTION)'

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    if OLD_LINE in content:
        final = content.replace(OLD_LINE, NEW_LINE)
        with open(FILE, 'w') as f: f.write(final)
        print("Disabled fetch_managed_spreads_loop.")
    else:
        print("Could not find line to disable.")
        # Debug
        if "# self.run_worker" in content:
            print("Already disabled?")

if __name__ == "__main__":
    patch()
