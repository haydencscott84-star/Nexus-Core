import sys
import os
import unittest
from nexus_copycat_bot import WhaleHunter

# Mock Data
TRADE_TEMPLATE = {
    "ticker": "SPY",
    "expiration": "2026-06-20",
    "strike": 560,
    "premium": 6_000_000, # > $5M Notional
    "volume": 6000,
    "open_interest": 1000,
    "type": "C",
    "delta": 0.50 # Default Valid
}

class TestCopycatLogic(unittest.TestCase):
    def setUp(self):
        self.hunter = WhaleHunter()

    def test_valid_delta(self):
        """Test that Delta 0.50 (50) triggers."""
        trade = TRADE_TEMPLATE.copy()
        trade['delta'] = 0.50
        print(f"\nTesting Valid Delta (0.50)...")
        sig = self.hunter.ingest_trade(trade)
        self.assertIsNotNone(sig, "Should trigger on Delta 0.50")
        print("✅ Triggered correctly.")

    def test_low_delta(self):
        """Test that Delta 0.30 (30) is rejected."""
        trade = TRADE_TEMPLATE.copy()
        trade['delta'] = 0.30
        print(f"\nTesting Low Delta (0.30)...")
        sig = self.hunter.ingest_trade(trade)
        self.assertIsNone(sig, "Should reject Delta 0.30 (<40)")
        print("✅ Rejected correctly.")

    def test_high_delta(self):
        """Test that Delta 0.70 (70) is rejected."""
        trade = TRADE_TEMPLATE.copy()
        trade['delta'] = 0.70
        print(f"\nTesting High Delta (0.70)...")
        sig = self.hunter.ingest_trade(trade)
        self.assertIsNone(sig, "Should reject Delta 0.70 (>60)")
        print("✅ Rejected correctly.")

    def test_delta_normalization(self):
        """Test that Delta 50 (already scaled) triggers."""
        trade = TRADE_TEMPLATE.copy()
        trade['delta'] = 50.0
        print(f"\nTesting Scaled Delta (50.0)...")
        sig = self.hunter.ingest_trade(trade)
        self.assertIsNotNone(sig, "Should trigger on Delta 50.0")
        print("✅ Triggered correctly.")

if __name__ == '__main__':
    unittest.main()
