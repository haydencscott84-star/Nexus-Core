import asyncio
import json
from unittest.mock import MagicMock, patch

# Mock dependencies
requests = MagicMock()

# Define a Test Class with the logic from ts_nexus.py
class TestNexus:
    def __init__(self):
        self.TS = MagicMock()
        self.TS._get_valid_access_token.return_value = "FAKE_TOKEN"
        self.TS.BASE_URL = "https://api.tradestation.com/v3"
        self.YOUR_ACCOUNT_ID = "12345678"
        self.DRY_RUN_EXEC = False

    def log_msg(self, msg):
        print(f"[LOG] {msg}")

    def file_log(self, msg):
        pass

    def parse_occ_to_ts_symbol(self, sym):
        return sym # Simple pass-through for test

    # COPIED FROM ts_nexus.py (with minor adjustments for self vars)
    async def execute_order(self, cmd, sym, qty, order_type="MARKET", limit_price=None):
        if not self.TS: return {"error": "No Auth"}
        ts_sym = self.parse_occ_to_ts_symbol(sym)
        if not ts_sym: return {"error": "Invalid Symbol"}

        headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}", "Content-Type": "application/json"}
        
        if cmd == "FORCE_EXIT": side = "SellToClose"
        else: side = "BuyToOpen" if cmd == "BUY" else "SellToClose"
        
        # THE FIX IS HERE: using 'side' instead of 'side.upper()'
        payload = {
            "AccountID": self.YOUR_ACCOUNT_ID, "Symbol": ts_sym, "Quantity": str(qty),
            "TradeAction": side, 
            "OrderType": "Market" if order_type == "MARKET" else "Limit",
            "TimeInForce": {"Duration": "DAY"}, "Route": "Intelligent"
        }
        if order_type != "MARKET" and limit_price: payload["LimitPrice"] = str(limit_price)

        self.file_log(f"API SENDING: {payload}")
        
        if self.DRY_RUN_EXEC:
            return {"status": "ok", "id": "SIM_ORDER_123"}

        try:
            url = "https://api.tradestation.com/v3/orderexecution/orders"
            # Mocking asyncio.to_thread(requests.post, ...)
            # In test we just call the mock directly
            r = requests.post(url, json=payload, headers=headers)
            
            if r.status_code > 299: 
                return {"error": r.text}
            
            resp = r.json()
            oid = "UNKNOWN"
            if "Orders" in resp and resp["Orders"]: oid = resp["Orders"][0].get("OrderID", "UNKNOWN")
            
            return {"status": "ok", "id": oid}
            
        except Exception as e: return {"error": str(e)}

async def verify_fix():
    print("--- VERIFYING ORDER EXECUTION PAYLOAD ---")
    
    app = TestNexus()
    
    # Mock requests.post response
    requests.post.return_value.status_code = 200
    requests.post.return_value.json.return_value = {"Orders": [{"OrderID": "ORDER_123"}]}
    
    # TEST 1: BUY ORDER
    print("\n[TEST 1] Sending BUY Order...")
    await app.execute_order("BUY", "SPY", 1, "MARKET")
    
    # Verify Payload
    args, kwargs = requests.post.call_args
    payload = kwargs['json']
    print(f"Payload Sent: {json.dumps(payload, indent=2)}")
    
    if payload['TradeAction'] == "BuyToOpen":
        print("✅ PASS: TradeAction is 'BuyToOpen'")
    else:
        print(f"❌ FAIL: TradeAction is '{payload['TradeAction']}' (Expected 'BuyToOpen')")

    # TEST 2: SELL ORDER
    print("\n[TEST 2] Sending SELL Order...")
    await app.execute_order("SELL", "SPY", 1, "LIMIT", 500.0)
    
    args, kwargs = requests.post.call_args
    payload = kwargs['json']
    print(f"Payload Sent: {json.dumps(payload, indent=2)}")
    
    if payload['TradeAction'] == "SellToClose":
        print("✅ PASS: TradeAction is 'SellToClose'")
    else:
        print(f"❌ FAIL: TradeAction is '{payload['TradeAction']}' (Expected 'SellToClose')")

if __name__ == "__main__":
    asyncio.run(verify_fix())
