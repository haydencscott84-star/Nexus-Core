
import unittest
import numpy as np
import datetime

class WhaleAlertLogic:
    def __init__(self, window_days=30):
        self.window = datetime.timedelta(days=window_days)
        self.history = [] # List of (timestamp, value)

    def process_trade(self, timestamp, value):
        """
        Returns (is_alert, z_score, mean, std)
        """
        # 1. Prune old data (Rolling Window: Time-Based)
        cutoff = timestamp - self.window
        self.history = [x for x in self.history if x[0] > cutoff]
        
        # 2. Calculate Stats on PRIOR history (Leakage Check: Exclude current)
        mean = 0.0
        std = 0.0
        z_score = 0.0
        is_alert = False
        
        if len(self.history) > 1:
            vals = [x[1] for x in self.history]
            mean = np.mean(vals)
            std = np.std(vals)
            
            # 3. The Trigger: (Current - Mean) / StdDev > 3.0
            if std > 0:
                z_score = (value - mean) / std
                if z_score > 3.0:
                    is_alert = True
        
        # 4. Update History (Current becomes Prior for next trade)
        self.history.append((timestamp, value))
        
        return is_alert, z_score, mean, std

class TestWhaleLogic(unittest.TestCase):
    def test_whale_alert(self):
        np.random.seed(42) # Deterministic
        logic = WhaleAlertLogic(window_days=30)
        base_time = datetime.datetime(2023, 1, 1)
        
        print("\n--- TEST: Normal Trading ---")
        # Feed 50 normal trades
        for i in range(50):
            ts = base_time + datetime.timedelta(hours=i)
            val = np.random.normal(100_000, 5_000) # Tighter std to avoid accidental outliers
            alert, z, m, s = logic.process_trade(ts, val)
            
            # Only assert no alert if we have enough history to be stable
            if i > 10:
                self.assertFalse(alert, f"False positive at step {i} (Val={val:.0f}, Mean={m:.0f}, Std={s:.0f}, Z={z:.2f})")
            
        print(f"Stats after 50 trades: Mean=${m:,.0f}, Std=${s:,.0f}")
        
        print("\n--- TEST: The Whale (3.5 Sigma) ---")
        # Inject a 3.5 Sigma Trade
        # Target = Mean + 3.5 * Std
        # If Mean=100k, Std=10k, Target=135k
        # Let's make it obvious: 200k
        
        whale_ts = base_time + datetime.timedelta(hours=51)
        whale_val = m + (3.5 * s) + 1000 # Slightly above 3.5 sigma
        
        alert, z, m_new, s_new = logic.process_trade(whale_ts, whale_val)
        
        print(f"Whale Trade: ${whale_val:,.0f}")
        print(f"Z-Score: {z:.2f}")
        
        self.assertTrue(alert, "Failed to trigger Red Alert on >3.0 sigma trade")
        self.assertTrue(z > 3.0, "Z-Score calculation incorrect")
        
        print(f"Whale Trade: ${whale_val:,.0f}")
        print(f"Z-Score: {z:.2f}")
        
        self.assertTrue(alert, "Failed to trigger Red Alert on >3.0 sigma trade")
        self.assertTrue(z > 3.0, "Z-Score calculation incorrect")
        
        # Verify Leakage: 
        # The Z-score should be exactly (whale_val - m_new) / s_new
        # where m_new and s_new are the stats of the history *excluding* the whale trade.
        
        expected_z = (whale_val - m_new) / s_new
        self.assertAlmostEqual(z, expected_z, places=5, msg="Z-Score does not match (Val-Mean)/Std. Possible logic error.")
        
        # Also verify that m_new does NOT include whale_val
        # We know m_new should be the mean of the previous 50 trades.
        # Let's verify that adding whale_val to the history *changes* the mean for the *next* step.
        
        # Manually calculate mean of history
        history_vals = [x[1] for x in logic.history] # This now includes whale_val
        mean_with_whale = np.mean(history_vals)
        
        self.assertNotAlmostEqual(m_new, mean_with_whale, delta=1.0, msg="Leakage! The mean used for Z-score includes the trade itself.")

    def test_time_window(self):
        print("\n--- TEST: Time Window Pruning ---")
        logic = WhaleAlertLogic(window_days=30)
        t1 = datetime.datetime(2023, 1, 1)
        logic.process_trade(t1, 100)
        
        t2 = datetime.datetime(2023, 2, 5) # > 30 days later
        logic.process_trade(t2, 100)
        
        # History should only have t2 now (t1 pruned)
        self.assertEqual(len(logic.history), 1, "Failed to prune old data > 30 days")

if __name__ == '__main__':
    unittest.main()
