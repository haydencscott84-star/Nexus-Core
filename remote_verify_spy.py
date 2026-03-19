import asyncio
import aiohttp
import sys

# MOCK Environment to simulate SpreadSniperApp logic with SPY data
class MockApp:
    def __init__(self):
        # Using SPY example as requested
        self.managed_spreads = {
            "SPY_TEST_PCS": {
                "short_sym": "SPY 550 P", "long_sym": "SPY 545 P",
                "short_strike": 550, "long_strike": 545,
                "qty": 5, "type": "PUT", "credit": True
            }
        }
    
    def log_msg(self, msg):
        print(f"LOG: {msg}")

    # Simulation of the PATCHED method
    async def announce_status_simulation(self, reason="VERIFICATION_RETRY"):
        try:
            sys.path.append('/root')
            from nexus_config import SNIPER_STATUS_WEBHOOK
            if not SNIPER_STATUS_WEBHOOK:
                print("No Webhook found!")
                return

            positions = []
            if self.managed_spreads:
                for sym, data in self.managed_spreads.items():
                    try:
                        k_short = data.get("short_strike", 0)
                        k_long = data.get("long_strike", 0)
                        
                        # [FIX] Logic Patch V2 Logic mimic
                        is_put = (data.get("type") == "PUT")
                        is_call = not is_put
                        is_credit = True # [FIX] Force Credit
                        strat_type = "Credit Put" if is_put else "Credit Call"
                        # [FIX] End
                        
                        qty = data.get("qty", 1)
                        strikes = f"{k_short}/{k_long}"
                        
                        # Stop Logic
                        stop_lvl = (k_short + 0.5) if is_put else (k_short - 0.5)
                        
                        pos_str = f"**{strat_type}** {strikes} (x{qty})\nSTOP: {stop_lvl:.2f} | PT: 50% Max | **ARMED**"
                        positions.append(pos_str)
                    except Exception as e:
                        print(f"Loop Error: {e}")
                        continue

            if not positions:
                msg = f"**Nexus Credit Status ({reason})**\nNo Open Positions."
            else:
                pos_block = "\n".join(positions)
                msg = f"**Nexus Credit Status ({reason})**\n{pos_block}\n*(Corrected SPY Verification Example)*"
            
            payload = {"content": msg}
            
            print(f"Sending to Discord...")
            async with aiohttp.ClientSession() as session:
                 async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                     if resp.status in [200, 204]:
                         self.log_msg(f"Status Announce Sent ({reason}) via Discord")
                     else:
                         self.log_msg(f"Discord Fail: {resp.status}")
        except Exception as e:
            self.log_msg(f"Announce Error: {e}")

async def main():
    app = MockApp()
    await app.announce_status_simulation()

if __name__ == "__main__":
    asyncio.run(main())
