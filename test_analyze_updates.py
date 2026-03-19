
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import pandas as pd
import datetime


# Define a dummy App class
class MockApp:
    def __init__(self, *args, **kwargs):
        pass
    def run_worker(self, *args, **kwargs):
        pass
    def log_msg(self, msg):
        pass
    def query_one(self, *args, **kwargs):
        return MagicMock()

# Mock dependencies
sys.modules["textual"] = MagicMock()
sys.modules["textual.app"] = MagicMock()
sys.modules["textual.app"].App = MockApp

sys.modules["textual.widgets"] = MagicMock()
sys.modules["textual.containers"] = MagicMock()
sys.modules["textual.reactive"] = MagicMock()
sys.modules["zmq"] = MagicMock()
sys.modules["zmq.asyncio"] = MagicMock()
sys.modules["nexus_lock"] = MagicMock()

# Import the module under test
import analyze_snapshots

class TestAnalyzeFetch(unittest.TestCase):
    def setUp(self):
        # Create instance
        self.app = analyze_snapshots.StrategicHUD()
        self.app.log_msg = MagicMock()
        self.app.write_log = MagicMock()
        self.app.last_spot_price = 600.0
        
        # Ensure directories exist
        os.makedirs("snapshots_spy", exist_ok=True)
        os.makedirs("snapshots_sweeps", exist_ok=True)

    @patch('analyze_snapshots.requests.get')
    @patch('analyze_snapshots.time.sleep')
    def test_fetch_cycle(self, mock_sleep, mock_get):
        print("\n[TEST] Verifying Fetch Logic & Staggering...")
        
        # Mock ORATS Response
        mock_orats_resp = MagicMock()
        mock_orats_resp.status_code = 200
        mock_orats_resp.json.return_value = {"data": [{
            "expiry": "2025-12-20", "dte": 10, "strike": 600,
            "callVolume": 100, "callOpenInterest": 500,
            "putVolume": 50, "putOpenInterest": 500,
            "delta": 0.5, "gamma": 0.02, "vega": 0.1, "theta": -0.05
        }]}
        
        # Mock UW Response
        mock_uw_resp = MagicMock()
        mock_uw_resp.status_code = 200
        mock_uw_resp.json.return_value = [{
            "expiry": "2025-12-20", "strike": 600,
            "call_volume": 100, "call_premium": 5000,
            "put_volume": 0, "put_premium": 0
        }]
        
        # Set side effects (First call ORATS, Second call UW)
        mock_get.side_effect = [mock_orats_resp, mock_uw_resp]
        
        # Run function
        self.app.fetch_and_save_snapshots()
        
        # Verify Stagger
        print(f"DEBUG: App Attributes: {dir(self.app)}")
        print(f"DEBUG: fetch_and_save_snapshots exists? {'fetch_and_save_snapshots' in dir(self.app)}")
        print(f"DEBUG: send_discord_alert exists? {'send_discord_alert' in dir(self.app)}")
        self.assertTrue('send_discord_alert' in dir(self.app), "send_discord_alert method is missing!")

        print(f"DEBUG: Mock Sleep Calls: {mock_sleep.mock_calls}")
        print(f"DEBUG: Write Log Calls: {self.app.write_log.mock_calls}")
        mock_sleep.assert_called_with(3)
        print("✅ Stagger Verified (3s sleep)")
        
        # Verify Files Created and Content
        spy_files = os.listdir("snapshots_spy")
        uw_files = os.listdir("snapshots_sweeps")
        self.assertTrue(len(spy_files) > 0, "SPY Snapshot created")
        self.assertTrue(len(uw_files) > 0, "UW Snapshot created")
        
        # Check Content for Greeks
        latest_spy = sorted(spy_files)[-1]
        df = pd.read_csv(f"snapshots_spy/{latest_spy}")
        print(f"Snapshot Content:\n{df.iloc[0]}")
        self.assertAlmostEqual(df.iloc[0]['gamma'], 0.02)
        self.assertAlmostEqual(df.iloc[0]['vega'], 0.1)
        
        print(f"✅ Snapshots Saved: {len(spy_files)} SPY, {len(uw_files)} UW")

if __name__ == '__main__':
    unittest.main()
