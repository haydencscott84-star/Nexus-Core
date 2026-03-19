
TARGET_FILE = "/root/nexus_spreads.py"

def fix_worker_call():
    try:
        with open(TARGET_FILE, 'r') as f:
            lines = f.readlines()
        
        new_lines = []
        for line in lines:
            if "self.run_worker(self.poll_orats_greeks)" in line:
                # Replace with explicit call and logging
                new_lines.append('        self.log_msg("Starting ORATS Worker...")\n')
                new_lines.append('        self.run_worker(self.poll_orats_greeks())\n')
            else:
                new_lines.append(line)
        
        with open(TARGET_FILE, 'w') as f:
            f.writelines(new_lines)
            print("Worker Call Fixed.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_worker_call()
