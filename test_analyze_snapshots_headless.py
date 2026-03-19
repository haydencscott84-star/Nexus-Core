import unittest
from unittest.mock import MagicMock, patch
import sys
import os
import pandas as pd
import json
import analyze_snapshots

class TestHeadlessLogic(unittest.TestCase):
    def test_logic_functions(self):
        print("\n[TEST] Verifying Headless Logic Functions...")
        
        # 1. Mock Data
        df = pd.DataFrame({
            'ticker': ['SPY', 'SPY', 'SPY'],
            'strike': [600, 605, 610],
            'type': ['CALL', 'PUT', 'CALL'],
            'vol': [1000, 2000, 500],
            'gamma': [0.05, 0.04, 0.03],
            'dte': [5, 5, 20],
            'premium': [10000, 20000, 5000],
            'is_bull': [True, False, True]
        })
        spot = 602.0
        
        # 2. Test Market Structure Metrics
        metrics = analyze_snapshots.calculate_market_structure_metrics(df, spot)
        print(f"  -> Flow Pain: {metrics['flow_pain']}")
        print(f"  -> Top GEX: {metrics['top_gex'].to_dict()}")
        
        self.assertGreater(metrics['flow_pain'], 0)
        self.assertFalse(metrics['top_gex'].empty)
        
        # 3. Test Trajectory
        traj = analyze_snapshots.calculate_trajectory_logic(spot, metrics['flow_pain'], metrics['top_gex'], df)
        print(f"  -> Trajectory: {traj}")
        self.assertIn("TRAJECTORY", traj)
        self.assertIn("Magnet", traj)
        self.assertIn("Drift", traj)
        
        # 4. Test Divergence
        # Mock daily stats
        daily_stats = pd.DataFrame({
            'is_fortress': [True, True, True],
            'is_bull': [True, True, True]
        })
        sentiment = 30 # Low sentiment
        
        div = analyze_snapshots.check_divergence_logic(daily_stats, sentiment)
        print(f"  -> Divergence: {div}")
        self.assertEqual(div, "BULL DIV")
        
        print("[PASS] Logic functions verified.")

if __name__ == '__main__':
    unittest.main()
