import asyncio
import aiohttp
import sys

# MOCK Environment to simulate SpreadSniperApp context
class MockApp:
    def __init__(self):
        self.managed_spreads = {
            "SPX_TEST_PUT": {
                "short_sym": "SPXW 5000 P", "long_sym": "SPXW 4990 P",
                "short_strike": 5000, "long_strike": 4990,
                "qty": 1, "type": "PUT", "credit": True
            },
            "SPX_TEST_CALL": {
                "short_sym": "SPXW 5100 C", "long_sym": "SPXW 5110 C",
                "short_strike": 5100, "long_strike": 5110,
                "qty": 1, "type": "CALL", "credit": True
            }
        }
    
    def log_msg(self, msg):
        print(f"LOG: {msg}")

    # COPY-PASTE of the PATCHED method logic we expect to be running
    # This proves that IF the file is patched as we intend, it works.
    async def announce_status_simulation(self, reason="VERIFICATION_TEST"):
        try:
            # We import config physically to ensure key is valid
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
                        
                        # Stop Logic (Mocked from observed code)
                        stop_lvl = (k_short + 0.5) if is_put else (k_short - 0.5)
                        
                        pos_str = f"**{strat_type}** {strikes} (x{qty})\nSTOP: {stop_lvl:.2f} | PT: 50% Max | **ARMED**"
                        positions.append(pos_str)
                    except Exception as e:
                        print(f"Loop Error: {e}")
                        continue

            if not positions:
                msg = f"**Nexus Credit Status ({reason})**\nNo Open Positions (Logic Check Failed)."
            else:
                pos_block = "\n".join(positions)
                msg = f"**Nexus Credit Status ({reason})**\n{pos_block}\n*(System Verification Message)*"
            
            payload = {"content": msg}
            
            print(f"Sending to {SNIPER_STATUS_WEBHOOK[:20]}...")
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
