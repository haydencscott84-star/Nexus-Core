
# PATCH DISCORD STATUS
# Target: nexus_debit_downloaded.py
# Objective: Announce Position Status on Launch, Open, Close.

import re

FILE = "nexus_debit_downloaded.py"

# 1. IMPORTS (Need requests if not present, though likely is)
# We need to make sure 'requests' is imported or we use aiohttp if available.
# Nexus Debit uses 'requests' in threaded calls usually? 
# Actually, let's use 'requests' with asyncio.to_thread to be safe/simple, or just aiohttp since we are async.
# 'nexus_debit.py' imports: import sys, os, asyncio, json, datetime, time...
# Let's verify imports first. Use robust approach: import inside method.

NEW_METHODS = r'''
    async def status_scheduler_loop(self):
        """Checks time for scheduled status announcements (Open/Close)."""
        while True:
            await asyncio.sleep(60) # Check every minute
            try:
                now_et = datetime.datetime.now(pytz.timezone('US/Eastern'))
                t_str = now_et.strftime("%H:%M")
                
                # Market Open (09:30)
                if t_str == "09:30":
                    await self.announce_status("MARKET_OPEN")
                    await asyncio.sleep(60) # Avoid double trigger
                    
                # Market Close (16:00)
                if t_str == "16:00":
                    await self.announce_status("MARKET_CLOSE")
                    await asyncio.sleep(60)
            except Exception as e:
                self.log_msg(f"Scheduler Error: {e}")

    async def announce_status(self, reason="UPDATE"):
        """Compiles active positions and posts to Discord."""
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK: return

            positions = []
            
            # Gather Managed Spreads
            if self.managed_spreads:
                for sym, data in self.managed_spreads.items():
                    # Format: "Debit Call: SPY 675/705 (3.0% Exp) - ARMED"
                    try:
                        k_long = data.get("long_strike", 0)
                        k_short = data.get("short_strike", 0)
                        is_call = data.get("is_call", True)
                        strat_type = "Debit Call" if is_call else "Debit Put"
                        
                        # Calculate PL / Exposure if possible (Need live data or cache)
                        # We use data from last update if available, or just static info
                        
                        # Exposure %
                        # We need 'val' which is in the TABLE, not necessarily in managed_spreads dict 
                        # unless we update it. Phase 10 update_positions does NOT update managed_spreads with Val.
                        # It only updates table.
                        # BUT managed_spreads has 'avg_price'.
                        
                        strikes = f"{k_long}/{k_short}"
                        stop_lvl = k_long * 0.99 if is_call else k_long * 1.01
                        
                        pos_str = f"**{strat_type}** {strikes}\nSTOP: {stop_lvl:.2f} | **ARMED**"
                        positions.append(pos_str)
                    except: continue

            if not positions:
                if reason == "LAUNCH":
                    msg = f"**Nexus Debit Online**\nNo Active Positions."
                else: 
                    return # Don't spam empty updates on schedule? User said "announce the position status", implying ONLY if exists? 
                    # "It will show Position: Debit Call..."
                    # If empty, maybe say "Flat"?
                    msg = f"**Nexus Debit Status ({reason})**\nNo Active Positions."
            else:
                pos_block = "\n".join(positions)
                msg = f"**Nexus Debit Status ({reason})**\n{pos_block}"
            
            payload = {"content": msg}
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                 async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                     if resp.status not in [200, 204]:
                         self.log_msg(f"Discord Fail: {resp.status}")
                     else:
                         self.log_msg(f"Status Announce Sent ({reason})")

        except Exception as e:
            self.log_msg(f"Announce Error: {e}")
'''

# We inject these methods before 'async def on_mount'
# And inside on_mount, we add:
# self.run_worker(self.status_scheduler_loop)
# self.call_later(announce_status, "LAUNCH") ? No, call_later expects sync or ...
# asyncio.create_task(self.announce_status("LAUNCH"))

def patch():
    with open(FILE, 'r') as f: content = f.read()

    # 1. Inject Methods
    if "async def status_scheduler_loop" not in content:
        # Find a good insertion point. Before 'async def on_mount' is standard.
        if "async def on_mount" in content:
            content = content.replace("async def on_mount", NEW_METHODS + "\n    async def on_mount")
            print("Injected status methods.")
        else:
            print("Could not find on_mount to inject methods before.")
            return

    # 2. Register in on_mount
    # Look for "self.run_worker(self.account_data_loop)"
    if "self.run_worker(self.account_data_loop)" in content:
        HOOK = "self.run_worker(self.account_data_loop)"
        INJECT = "        self.run_worker(self.status_scheduler_loop)\n        self.run_worker(lambda: self.announce_status('LAUNCH'))"
        # Using lambda for run_worker to call async method once? 
        # Textual run_worker accepts coroutines.
        # So: self.run_worker(self.announce_status('LAUNCH')) is wrong because it calls it immediately and passes result?
        # No, run_worker(awaitable) or run_worker(func).
        # use: self.run_worker(self.announce_status, "LAUNCH") ? arguments?
        # Textual run_worker: run_worker(awaitable, ...)
        # So: self.run_worker(self.announce_status("LAUNCH")) works if it returns coroutine.
        
        INJECT = HOOK + "\n" + '        self.run_worker(self.status_scheduler_loop)\n        self.run_worker(self.announce_status("LAUNCH"))'
        
        # ACTUALLY, replace original line so we don't duplicate if run multiple times?
        # Better: use replace unique
        if "status_scheduler_loop" not in content.split("async def on_mount")[1]: 
             content = content.replace(HOOK, HOOK + "\n        self.run_worker(self.status_scheduler_loop)\n        self.run_worker(self.announce_status('LAUNCH'))")
             print("Registered workers in on_mount.")

    with open(FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch()
