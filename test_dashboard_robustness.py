import unittest
from unittest.mock import MagicMock
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

# Define custom mocks to avoid MagicMock inheritance issues
class MockApp:
    CSS = ""
    def __init__(self, *args, **kwargs):
        pass
    def run_worker(self, *args, **kwargs):
        pass
    def log_msg(self, msg):
        pass
    def query_one(self, selector, type=None):
        return MagicMock()

class MockWidget:
    def __init__(self, *args, **kwargs):
        pass

class MockContainer(MockWidget):
    pass

class MockStyles:
    def __init__(self):
        self.display = "block"

class MockButton(MockWidget):
    class Pressed:
        pass
    def __init__(self, label, id=None, variant=None, disabled=False, classes=None):
        self.label = label
        self.id = id
        self.variant = variant
        self.disabled = disabled
        self.classes = classes
        self.styles = MockStyles()

class MockInput(MockWidget):
    class Changed:
        pass

class MockDataTable(MockWidget):
    class RowSelected:
        pass

# Mock modules
sys.modules["textual"] = MagicMock()
sys.modules["textual.app"] = MagicMock()
sys.modules["textual.app"].App = MockApp
sys.modules["textual.widgets"] = MagicMock()
sys.modules["textual.widgets"].Button = MockButton
sys.modules["textual.widgets"].DataTable = MockDataTable
sys.modules["textual.widgets"].Header = MagicMock()
sys.modules["textual.widgets"].Footer = MagicMock()
sys.modules["textual.widgets"].Log = MagicMock()
sys.modules["textual.widgets"].Input = MockInput
sys.modules["textual.widgets"].Label = MagicMock()
sys.modules["textual.widgets"].Static = MockWidget
sys.modules["textual.containers"] = MagicMock()
sys.modules["textual.containers"].Horizontal = MockContainer
sys.modules["textual.containers"].Vertical = MockContainer
sys.modules["textual.containers"].Container = MockContainer
sys.modules["textual.reactive"] = MagicMock()
# Mock reactive to return the initial value
sys.modules["textual.reactive"].reactive = lambda x: x
sys.modules["textual.binding"] = MagicMock()
# Mock @on decorator to be a pass-through
def mock_on(*args, **kwargs):
    def decorator(func):
        return func
    return decorator
sys.modules["textual"].on = mock_on

sys.modules["zmq"] = MagicMock()
sys.modules["zmq.asyncio"] = MagicMock()

# Import the class
from trader_dashboard import TraderDashboardV2

class TestDashboardRobustness(unittest.TestCase):
    def setUp(self):
        self.app = TraderDashboardV2()
        self.app.log_msg = MagicMock()
        self.app.query_one = MagicMock()
        
        # Mock DataTable
        self.dt = MagicMock()
        self.dt.rows = {}
        # Configure query_one to return self.dt by default
        self.app.query_one.return_value = self.dt

    def test_update_orders_table_robustness(self):
        """Test that update_orders_table handles malformed data without crashing."""
        print("\n[TEST] Verifying Order Table Robustness...")
        
        # 1. Normal Order
        orders_normal = [{"OrderID": "1", "Symbol": "SPY", "TradeAction": "Buy", "Status": "ACK"}]
        try:
            self.app.update_orders_table(orders_normal)
            print("  [PASS] Normal Order handled")
        except Exception as e:
            self.fail(f"Normal order crashed: {e}")

        # 2. Missing TradeAction (The crash culprit)
        orders_missing_key = [{"OrderID": "2", "Symbol": "SPY", "Status": "ACK"}]
        try:
            self.app.update_orders_table(orders_missing_key)
            print("  [PASS] Missing TradeAction handled (No Crash)")
        except Exception as e:
            self.fail(f"Missing TradeAction crashed: {e}")

        # 3. Missing Symbol
        orders_no_sym = [{"OrderID": "3", "TradeAction": "Sell", "Status": "ACK"}]
        try:
            self.app.update_orders_table(orders_no_sym)
            print("  [PASS] Missing Symbol handled")
        except Exception as e:
            self.fail(f"Missing Symbol crashed: {e}")
            
        # 4. Empty Order
        orders_empty = [{"OrderID": "4"}]
        try:
            self.app.update_orders_table(orders_empty)
            print("  [PASS] Empty Order handled")
        except Exception as e:
            self.fail(f"Empty Order crashed: {e}")

    def test_on_ord_click_crash_fix(self):
        """Test that clicking an order attempts to show the cancel button."""
        print("\n[TEST] Verifying Order Click Robustness...")
        
        # Mock event
        event = MagicMock()
        event.row_key.value = "123"
        
        # Mock the Cancel Button
        btn_cancel = MockButton("CANCEL ORDER", id="btn-cancel")
        btn_cancel.styles.display = "none" # Initial state
        print(f"DEBUG: btn_cancel ID in test: {id(btn_cancel)}")
        
        # Configure query_one to return btn_cancel when asked for it
        def query_side_effect(selector, **kwargs):
            print(f"DEBUG: query_one called with '{selector}'")
            if "btn-cancel" in selector: 
                print(f"DEBUG: Returning btn_cancel {id(btn_cancel)}")
                return btn_cancel
            print("DEBUG: Returning self.dt")
            return self.dt
            
        self.app.query_one.side_effect = query_side_effect
        
        try:
            print("DEBUG: Calling on_ord_click")
            self.app.on_ord_click(event)
            print("DEBUG: Returned from on_ord_click")
            print(f"DEBUG: btn_cancel.styles.display = {btn_cancel.styles.display}")
            
            print("  [PASS] Order Click handled (No Crash)")
            # Verify it tried to show the button
            self.assertEqual(btn_cancel.styles.display, "block")
        except Exception as e:
            print(f"DEBUG: Exception: {e}")
            self.fail(f"Order Click crashed: {e}")

if __name__ == '__main__':
    unittest.main()
