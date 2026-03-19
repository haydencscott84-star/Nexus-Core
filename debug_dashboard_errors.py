import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock, patch

# Add script dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock dependencies
sys.modules['nexus_lock'] = MagicMock()
sys.modules['zmq'] = MagicMock()
sys.modules['zmq.asyncio'] = MagicMock()

from trader_dashboard import TraderDashboardV2, ExecutionPanel
from textual.widgets import DataTable, Input

async def verify_fixes():
    print("--- VERIFYING DASHBOARD FIXES ---")
    
    app = TraderDashboardV2()
    app.zmq_ctx = MagicMock()
    app.ex = AsyncMock()
    app.pub = MagicMock() # Mock Control Socket
    
    # Mock UI
    mock_table = MagicMock(spec=DataTable)
    mock_table.rows = {} # Simulate rows dict
    
    # Mock query_one to return our mock table
    def query_side_effect(selector, type=None):
        if selector == "#tbl-ord": return mock_table
        if selector == ExecutionPanel: return app.execution_panel
        return MagicMock()
    
    app.query_one = MagicMock(side_effect=query_side_effect)
    
    # 1. Verify Update Logic (Smart Diff)
    print("\n[TEST 1] Smart Table Update...")
    
    # Initial State: Order 1001 exists
    row_key_1001 = MagicMock()
    row_key_1001.value = "1001"
    mock_table.rows = {row_key_1001: MagicMock()} 
    
    orders = [
        {"OrderID": "1001", "Symbol": "SPY", "TradeAction": "Buy", "Status": "Open"}, # Existing
        {"OrderID": "1002", "Symbol": "SPY", "TradeAction": "Sell", "Status": "Open"} # New
    ]
    
    app.update_orders_table(orders)
    
    # Check calls
    # remove_row should NOT be called for 1001
    # add_row should be called for 1002
    # add_row should NOT be called for 1001 (unless we decided to update it, but my logic skips existing)
    
    # Verify remove_row
    mock_table.remove_row.assert_not_called()
    
    # Verify add_row
    args_list = mock_table.add_row.call_args_list
    print(f"Add Row Calls: {len(args_list)}")
    
    added_ids = [c[1]['key'] for c in args_list]
    print(f"Added IDs: {added_ids}")
    
    if "1002" in added_ids and "1001" not in added_ids:
        print("✅ PASS: Smart Update (Added new, skipped existing)")
    else:
        print("❌ FAIL: Smart Update Logic Incorrect")

    # 2. Verify Data Population (on_pos_click)
    print("\n[TEST 2] Position Click Population...")
    
    # Setup Execution Panel Mock
    app.execution_panel = ExecutionPanel()
    # We need to mock query_one inside ExecutionPanel too
    app.execution_panel.query_one = MagicMock()
    
    # Setup Pos Map
    app.pos_map = {
        "SPY_OPT": {
            "sym": "SPY_OPT",
            "stk": 500,
            "dte": 30,
            "typ": "C",
            "mkt": 5.50,
            "qty": 10,
            "desc": "SPY 500C"
        }
    }
    
    # Simulate Click Event
    event = MagicMock()
    event.row_key.value = "SPY_OPT"
    
    app.on_pos_click(event)
    
    xp = app.execution_panel
    print(f"Panel State: Sym={xp.sym}, Stk={xp.stk}, Price={xp.price}")
    
    if xp.sym == "SPY_OPT" and xp.stk == 500 and xp.price == 5.50:
        print("✅ PASS: Execution Panel Populated")
    else:
        print("❌ FAIL: Execution Panel Data Mismatch")

if __name__ == "__main__":
    asyncio.run(verify_fixes())
