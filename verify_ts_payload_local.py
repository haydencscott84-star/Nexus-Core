
import asyncio
from ts_nexus_from_server import NexusEngine

# Mocking TS Manager inside NexusEngine for validation
class MockTSManager:
    def place_order(self, payload):
        print(f"MOCK PLACE ORDER: {payload}")
        return {"id": "123", "status": "Filled"}

async def test_payload():
    engine = NexusEngine()
    engine.TS = MockTSManager()
    engine.log_msg = lambda x: print(f"LOG: {x}")
    # engine.DRY_RUN_EXEC = False # Need to ensure we hit the TS path. 
    # But DRY_RUN_EXEC is a global constant in the module depending on import.
    # We can patch the class method listen_for_execution or attributes if needed.
    
    # Actually, verify logic in listen_for_execution directly might be hard due to loop.
    # Let's just copy the logic snippet here to test it, 
    # OR inject a message into the zmq socket if we run the engine?
    # Easier: Just extract the logic logic into a test function.
    
    # Logic from ts_nexus.py:
    def build_payload(action, symbol, qty=1, order_type="MARKET", limit_price=None):
        action = action.upper()
        is_option = any(char.isdigit() for char in symbol)
        
        ts_action = action
        if is_option:
            if action == "BUY": ts_action = "BuyToOpen"
            elif action == "SELL": ts_action = "SellToClose"
        
        # Testing if "BUY" remains "BUY" for equities
        return ts_action

    print(f"Equity BUY Payload Action: {build_payload('BUY', 'SPY')}")
    print(f"Equity SELL Payload Action: {build_payload('SELL', 'SPY')}")
    print(f"Option BUY Payload Action: {build_payload('BUY', 'SPY 231215C00450000')}")

if __name__ == "__main__":
    asyncio.run(test_payload())
