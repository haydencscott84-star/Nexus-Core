import re

TARGET_FILE = "/root/trader_dashboard.py"

# 1. LOOP METHOD
DISCORD_LOOP = """
    async def discord_report_loop(self):
        \"\"\"Sends Delta/Gamma status to Discord every 30 minutes during market hours.\"\"\"
        self.log_msg("DISCORD: Reporter Loop Started (30m Interval)")
        while True:
            try:
                # 1. Market Hours Check (Simple Eastern Time approx)
                # Assuming server is UTC, ET is UTC-5 (Standard) or UTC-4 (DST).
                # Safer to rely on system time if it's set to ET, or use offset.
                # Nexus Config usually handles timezone. Let's assume server local time is relevant.
                now = datetime.datetime.now()
                # Trading Hours: 09:30 - 16:00
                is_market = False
                if now.weekday() < 5: # Mon-Fri
                    t_start = now.replace(hour=9, minute=30, second=0, microsecond=0)
                    t_end = now.replace(hour=16, minute=0, second=0, microsecond=0)
                    if t_start <= now <= t_end:
                        is_market = True
                
                # Verify ORATS data exists
                has_data = hasattr(self, 'orats_chain') and not self.orats_chain.empty
                
                if is_market and has_data:
                    nd, ng = self.calculate_net_delta()
                    
                    # Log internal check
                    self.log_msg(f"DISCORD: Sending Report (D:{nd:.0f} G:{ng:.0f})")
                    
                    payload = {
                        "username": "Antigravity Risk Manager",
                        "avatar_url": "https://i.imgur.com/4M34hi2.png",
                        "embeds": [{
                            "title": "🛡️ Portfolio Risk Snapshot",
                            "color": 15158332 if ng < -100 else 3066993, # Red if High Gamma Risk, else Green
                            "fields": [
                                {"name": "NET DELTA (Speed)", "value": f"**{nd:+.0f}**", "inline": True},
                                {"name": "NET GAMMA (Accel)", "value": f"**{ng:+.0f}**", "inline": True},
                                {"name": "SPY Price", "value": f"${self.query_one(ExecutionPanel).und_price:.2f}", "inline": True}
                            ],
                            "footer": {"text": "Nexus Options Suite • Antigravity Module"}
                        }]
                    }
                    
                    # Offload request to executor to avoid blocking loop
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: requests.post(DISCORD_WEBHOOK_URL, json=payload))
                    
                else:
                    # Log wait (verbose mode only?)
                    # self.log_msg(f"DISCORD: Skip (Market={is_market}, Data={has_data})")
                    pass

            except Exception as e:
                self.log_msg(f"DISCORD ERR: {e}")
            
            # Wait 30 Minutes
            await asyncio.sleep(1800)
"""

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Add Imports
    if "import requests" not in content:
        print("Injecting 'import requests'...")
        content = content.replace("import zmq, zmq.asyncio", "import requests, zmq, zmq.asyncio")

    # 2. Add Config Import
    if "DISCORD_WEBHOOK_URL" not in content:
        print("Injecting DISCORD_WEBHOOK_URL import...")
        content = content.replace("from nexus_config import is_sleep_mode", "from nexus_config import is_sleep_mode, DISCORD_WEBHOOK_URL")

    # 3. Add Method
    if "async def discord_report_loop" not in content:
        print("Injecting discord_report_loop method...")
        # Inject before sub_mkt
        content = content.replace("async def sub_mkt(self):", DISCORD_LOOP + "\n    async def sub_mkt(self):")

    # 4. Add Start Call
    # Look for `self.orats_chain = pd.DataFrame()` inside sub_mkt (added in previous patch)
    if "create_task(self.discord_report_loop())" not in content:
        print("Injecting start call...")
        content = content.replace("asyncio.create_task(self.fetch_orats_greeks())", 
                                  "asyncio.create_task(self.fetch_orats_greeks()); asyncio.create_task(self.discord_report_loop())")

    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
