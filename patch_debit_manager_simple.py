
# PATCH DEBIT MANAGER SIMPLE
# Target: nexus_debit_downloaded.py
# Replace auto_manager_loop with Guarded Version

FILE = "nexus_debit_downloaded.py"

NEW_MANAGER = r'''
    async def auto_manager_loop(self):
        """
        THE HYBRID MANAGER (Phase 10 Logic)
        1. OFFENSE: 50% Profit (1.5x on Debit)
        2. DEFENSE: 1% Strike Stop
        """
        while True:
            await asyncio.sleep(1)
            if not self.auto_exit_enabled or not self.managed_spreads:
                continue

            # Copy to avoid size change during iteration check, though usually safe if not deleting
            # But update_positions replaces the whole dict, so we might encounter concurrency issues?
            # It's running on main thread (async), so no thread concurrency, but await calls yield.
            # Safe to iterate.
            
            for key, spread in list(self.managed_spreads.items()):
                long_strike = spread.get("long_strike", 0)
                
                # SAFETY GUARD: Zero Strike
                if long_strike <= 0: continue
                
                entry_debit = abs(spread.get("avg_price", 0))
                is_call = spread.get("is_call", True) # Default True if missing, but we sync it.
                
                # Logic: 1% Rule
                if is_call: stop_level = long_strike * 0.99
                else: stop_level = long_strike * 1.01
                
                # Trigger
                if self.current_spy_price > 0:
                    triggered = False
                    if is_call and self.current_spy_price <= stop_level: triggered = True
                    if not is_call and self.current_spy_price >= stop_level: triggered = True
                    
                    if triggered:
                        self.log_msg(f"ðŸ›‘ STOP TRIGGERED: SPY {self.current_spy_price:.2f} hit limit {stop_level:.2f}")
                        await self.panic_close_spread(spread, reason="STOP_LOSS")
'''

def patch_manager():
    with open(FILE, 'r') as f: lines = f.readlines()
    
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if "async def auto_manager_loop(self):" in line:
            start_idx = i
        
        # End is start of next method or EOF
        if start_idx != -1 and i > start_idx:
            if "async def" in line or "def " in line:
                # But wait, auto_manager_loop might be the last method?
                # Check indentation.
                # If "async def" is at indentation 4 (class level), it's a new method.
                if line.startswith("    async def") or line.startswith("    def"):
                    end_idx = i
                    break
    
    # If no next method, assume end of class/file? 
    # Usually fetch_chain is after it? (From previous view, fetch_chain was after it).
    
    if start_idx != -1:
        if end_idx == -1: end_idx = len(lines)
        
        # Replace
        new_lines = [l + "\n" for l in NEW_MANAGER.splitlines() if l.strip() != ""] # preserve internal newlines
        
        # Actually use split not splitlines to keep \n? NO.
        # Just reconstruction.
        new_lines = []
        for l in NEW_MANAGER.split("\n"):
            if not l and len(new_lines) == 0: continue # skip leading empty
            new_lines.append(l + "\n")

        final_lines = lines[:start_idx] + new_lines + lines[end_idx:]
        with open(FILE, 'w') as f: f.writelines(final_lines)
        print("Patched auto_manager_loop successfully.")
    else:
        print("Could not find auto_manager_loop.")

if __name__ == "__main__":
    patch_manager()
