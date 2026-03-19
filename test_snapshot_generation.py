import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import pandas as pd
import shutil
import datetime

# Mock dependencies BEFORE importing the module
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
    def call_from_thread(self, f, *args):
        f(*args)
    def set_timer(self, *args):
        pass
    def notify(self, *args):
        pass

sys.modules["textual"] = MagicMock()
sys.modules["textual.app"] = MagicMock()
sys.modules["textual.app"].App = MockApp
sys.modules["textual.widgets"] = MagicMock()
sys.modules["textual.containers"] = MagicMock()
sys.modules["textual.reactive"] = MagicMock()
# Mock reactive to return initial value
sys.modules["textual.reactive"].reactive = lambda x: x
sys.modules["textual"].work = lambda **kwargs: lambda f: f # Mock @work decorator

sys.modules["zmq"] = MagicMock()
sys.modules["zmq.asyncio"] = MagicMock()
sys.modules["nexus_lock"] = MagicMock() # Prevent singleton check

# Import the module
import viewer_dash_nexus

class TestSnapshotGeneration(unittest.TestCase):
    def setUp(self):
        self.dash = viewer_dash_nexus.MacroDash()
        self.dash.log_msg = MagicMock()
        # Mock call_from_thread to execute immediately
        self.dash.call_from_thread = lambda f, *args: f(*args)
        
        # Ensure directories exist
        os.makedirs("snapshots_spy", exist_ok=True)
        os.makedirs("snapshots_sweeps", exist_ok=True)

    def test_save_snapshot_data(self):
        print("\n[TEST] Verifying Snapshot Generation...")
        
        # 1. Prepare Sample Data
        orats_data = [{
            "expiry": "2025-12-20", "dte": 18, "strike": 600.0,
            "callVolume": 100, "callOpenInterest": 500, "callDelta": 0.5, "callGamma": 0.01,
            "putVolume": 200, "putOpenInterest": 600, "putDelta": -0.4, "putGamma": 0.02,
            "callBid": 1.0, "callAsk": 1.1, "putBid": 2.0, "putAsk": 2.1
        }]
        
        uw_data = [{
            "expiry": "2025-12-20", "strike": 600.0,
            "call_volume": 50, "put_volume": 0,
            "call_premium": 5000, "put_premium": 0
        }]
        
        price = 595.50
        
        # 2. Call the method
        self.dash.save_snapshot_data(orats_data, uw_data, price)
        
        # 3. Verify SPY Snapshot
        # Find the most recently created file
        spy_files = sorted([
            os.path.join("snapshots_spy", f) 
            for f in os.listdir("snapshots_spy") 
            if f.endswith(".csv")
        ], key=os.path.getmtime)
        
        self.assertTrue(len(spy_files) > 0, "SPY snapshot not created")
        latest_spy = spy_files[-1]
        print(f"  -> Checking SPY Snapshot: {latest_spy}")
        
        df_spy = pd.read_csv(latest_spy)
        print(f"  -> SPY Columns: {list(df_spy.columns)}")
        
        # Validations
        self.assertIn("underlying_price", df_spy.columns)
        self.assertEqual(float(df_spy.iloc[0]['underlying_price']), 595.50)
        self.assertEqual(len(df_spy), 2) # Call and Put row
        self.assertEqual(df_spy.iloc[0]['symbol'], 'SPY')
        self.assertEqual(df_spy.iloc[0]['vol'], 100) # Call Vol
        
        # 4. Verify UW Snapshot
        uw_files = sorted([
            os.path.join("snapshots_sweeps", f) 
            for f in os.listdir("snapshots_sweeps") 
            if f.endswith(".csv")
        ], key=os.path.getmtime)
        
        self.assertTrue(len(uw_files) > 0, "UW snapshot not created")
        latest_uw = uw_files[-1]
        print(f"  -> Checking UW Snapshot: {latest_uw}")
        
        df_uw = pd.read_csv(latest_uw)
        print(f"  -> UW Columns: {list(df_uw.columns)}")
        
        # Validations
        self.assertIn("total_premium", df_uw.columns)
        self.assertEqual(df_uw.iloc[0]['total_premium'], 5000)
        self.assertEqual(df_uw.iloc[0]['parsed_type'], 'CALL')
        
        print("[PASS] Snapshots generated correctly.")

if __name__ == '__main__':
    unittest.main()
