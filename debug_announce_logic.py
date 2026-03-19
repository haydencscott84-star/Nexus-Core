
import asyncio
import aiohttp
from datetime import datetime

# MOCK DATA TABLE
class MockRow:
    def __init__(self, data):
        self.data = data
    def __getitem__(self, idx):
        return self.data[idx]

class MockTable:
    def __init__(self):
        self.rows = ["row1"]
    def get_row(self, key):
        # STRATEGY, STRIKES, DTE, QTY, P/L OPEN, EXPOSURE, STOP, PT
        return ["CREDIT PUT", "700/690", "28d", "10", "+15%", "10%", "699.5", "50%"]

class MockApp:
    def query_one(self, selector, type_):
        if selector == "#positions_table":
            return MockTable()
        raise Exception("Not Found")

    async def announce_status(self, reason="DEBUG"):
        print(f"--- TESTING ANNOUNCE_STATUS ({reason}) ---")
        try:
            from nexus_config import SNIPER_STATUS_WEBHOOK
            print(f"WEBHOOK: {SNIPER_STATUS_WEBHOOK[:10]}...")
            if not SNIPER_STATUS_WEBHOOK: 
                print("NO WEBHOOK")
                return

            positions = []
            
            # WYSIWYG: Pull directly from table
            try:
                table = self.query_one("#positions_table", None)
                for row_key in table.rows:
                    row_data = table.get_row(row_key)
                    
                    def to_str(item):
                        if hasattr(item, "plain"): return item.plain
                        return str(item)
                        
                    strat = to_str(row_data[0])
                    strikes = to_str(row_data[1])
                    qty = to_str(row_data[3])
                    stop = to_str(row_data[6])
                    
                    pos_str = f"**{strat}** {strikes} (x{qty})\nSTOP: {stop} | PT: 50% Max | **ARMED**"
                    positions.append(pos_str)
            except Exception as e: 
                print(f"TABLE ERROR: {e}")
                import traceback
                traceback.print_exc()

            if not positions:
                msg = "No Positions"
            else:
                pos_block = "\n".join(positions)
                msg = f"**Nexus Status ({reason})**\n{pos_block}"
            
            print(f"SENDING MSG: {msg}")
            
            async with aiohttp.ClientSession() as session:
                payload = {"content": msg}
                async with session.post(SNIPER_STATUS_WEBHOOK, json=payload) as resp:
                    print(f"RESP: {resp.status}")
                    text = await resp.text()
                    print(f"TEXT: {text}")
        except Exception as e:
            print(f"MAIN ERROR: {e}")
            import traceback
            traceback.print_exc()

async def run():
    app = MockApp()
    await app.announce_status()

if __name__ == "__main__":
    asyncio.run(run())
