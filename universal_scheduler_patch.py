
import re

SCHEDULER_METHOD = """    async def status_scheduler_loop(self):
        # Wait for Table Population
        await asyncio.sleep(15)
        await self.announce_status("READY")
        
        while True:
            await asyncio.sleep(1800) # 30 Minutes
            try:
                await self.announce_status("HEARTBEAT")
            except: pass
"""

def patch_file(path, new_code):
    try:
        with open(path, 'r') as f:
            content = f.readlines()
            
        new_lines = []
        skip = False
        patched = False
        
        # Target: async def status_scheduler_loop(self):
        target = "    async def status_scheduler_loop(self):"
        
        for line in content:
            if target in line:
                new_lines.append(new_code)
                skip = True
                patched = True
                continue
                
            if skip:
                # Deduct end of method by indentation
                if line.strip() and not line.startswith('    '):
                    skip = False
                    new_lines.append(line)
                elif re.match(r'    (async )?def ', line):
                    skip = False
                    new_lines.append(line)
                continue
                
            new_lines.append(line)
            
        with open(path, 'w') as f:
            f.writelines(new_lines)
            
        if patched: print(f"SUCCESS: {path}")
        else: print(f"NOT_FOUND: {path}")

    except Exception as e:
        print(f"ERROR {path}: {e}")

if __name__ == "__main__":
    patch_file('/root/nexus_spreads.py', SCHEDULER_METHOD)
    patch_file('/root/nexus_debit.py', SCHEDULER_METHOD)
