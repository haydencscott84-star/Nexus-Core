import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Add script dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock dependencies
sys.modules['nexus_lock'] = MagicMock()
# We need real Textual for widget verification
# But we mock ZMQ
sys.modules['zmq'] = MagicMock()
sys.modules['zmq.asyncio'] = MagicMock()

from trader_dashboard import TraderDashboardV2
from textual.widgets import DataTable

async def verify_logic():
    print("--- VERIFYING OPEN ORDER MANAGEMENT ---")
    
    app = TraderDashboardV2()
    app.zmq_ctx = MagicMock()
    app.ex = AsyncMock() # Mock Execution Socket
    app.log_msg = MagicMock() # Mock Logging to avoid UI errors
    
    # 1. Verify Table Update
    print("\n[TEST 1] Updating Orders Table...")
    
    # Mock UI query
    mock_table = MagicMock(spec=DataTable)
    mock_table.rows = {}
    
    # We need to patch query_one because the app isn't mounted
    app.query_one = MagicMock(return_value=mock_table)
    
    orders = [
        {
            "OrderID": "1001",
            "Symbol": "SPY",
            "TradeAction": "BuyToOpen",
            "Quantity": 5,
            "OrderType": "Limit",
            "LimitPrice": 500.50,
            "Status": "Open"
        }
    ]
    
    app.update_orders_table(orders)
    
    # Check if clear() and add_row() were called
    mock_table.clear.assert_called_once()
    mock_table.add_row.assert_called()
    
    args, kwargs = mock_table.add_row.call_args
    print(f"Row Added: {args}")
    
    if "1001" in args and "SPY" in args:
        print("✅ PASS: Order Data populated correctly.")
    else:
        print("❌ FAIL: Order Data missing or incorrect.")

    # 2. Verify Cancel Logic
    print("\n[TEST 2] Sending Cancel Command...")
    
    # Mock recv_json response
    app.ex.recv_json.return_value = {"status": "ok"}
    
    await app.send_cancel("1001")
    
    # Verify send_json call
    app.ex.send_json.assert_called_once()
    args, kwargs = app.ex.send_json.call_args
    payload = args[0]
    print(f"Payload Sent: {payload}")
    
    if payload.get("cmd") == "CANCEL_ORDER" and payload.get("order_id") == "1001":
        print("✅ PASS: Cancel Command sent correctly.")
    else:
        print("❌ FAIL: Cancel Command malformed.")

if __name__ == "__main__":
    asyncio.run(verify_logic())
