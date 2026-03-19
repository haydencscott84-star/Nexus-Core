import unittest
import pandas as pd
import numpy as np
from watchtower_engine import calculate_metrics

class TestWatchtower(unittest.TestCase):
    
    def create_mock_data(self, spy_trend, vix_val, vix3m_val, rsp_trend):
        # Create 100 days of data
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100)
        data = {
            "SPY": np.linspace(500, 500 * (1+spy_trend), 100),
            "RSP": np.linspace(160, 160 * (1+rsp_trend), 100),
            "^VIX": np.full(100, vix_val),
            "^VIX3M": np.full(100, vix3m_val),
            "^VVIX": np.full(100, 100)
        }
        return pd.DataFrame(data, index=dates)

    def test_crash_scenario(self):
        print("\n🧪 Testing CRASH SCENARIO (Red Light)...")
        # SPY Down 10%, VIX 40, VIX3M 35 (Inverted)
        df = self.create_mock_data(spy_trend=-0.10, vix_val=40, vix3m_val=35, rsp_trend=-0.10)
        result = calculate_metrics(df)
        
        print(f"   Result: {result['regime']} | Alert: {result['alert_level']}")
        self.assertEqual(result['alert_level'], "RED")
        self.assertTrue(result['consensus_votes']['term_structure_inverted'])
        self.assertIn("BEAR", result['regime'])

    def test_breadth_divergence(self):
        print("\n🧪 Testing BREADTH DIVERGENCE (Yellow Light)...")
        # Create base data
        df = self.create_mock_data(spy_trend=0.05, vix_val=15, vix3m_val=18, rsp_trend=-0.05)
        
        # MANIPULATE THE LAST 10 DAYS TO FORCE DIVERGENCE
        # SPY pumps 2% in last 10 days
        df.iloc[-10:, df.columns.get_loc("SPY")] = df.iloc[-11]["SPY"] * np.linspace(1.0, 1.02, 10)
        
        # RSP dumps 2% in last 10 days
        df.iloc[-10:, df.columns.get_loc("RSP")] = df.iloc[-11]["RSP"] * np.linspace(1.0, 0.98, 10)
        
        result = calculate_metrics(df)
        
        print(f"   Result: {result['regime']} | Alert: {result['alert_level']}")
        self.assertEqual(result['alert_level'], "YELLOW")
        self.assertTrue(result['consensus_votes']['breadth_divergence'])
        self.assertEqual(result['regime'], "BULL_QUIET") # Price is high, VIX low

if __name__ == '__main__':
    unittest.main()
