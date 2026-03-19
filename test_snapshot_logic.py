
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class SnapshotLogic:
    def calculate_vwap(self, premium_sum, volume_sum):
        """
        VWAP = Total Premium / Total Volume
        """
        if volume_sum == 0: return 0.0
        return premium_sum / volume_sum

    def scale_spot_price(self, ticker, price):
        """
        If SPX, ensure price is ~6000 range.
        If SPY, ensure price is ~600 range.
        """
        if ticker == "SPX" and price < 1000:
            return price * 10
        if ticker == "SPY" and price > 1000:
            return price / 10
        return price

    def filter_heatmap_range(self, strikes, spot_price):
        """
        Filter strikes within +/- 10% of spot price.
        """
        lower = spot_price * 0.90
        upper = spot_price * 1.10
        return [s for s in strikes if lower <= s <= upper]

    def generate_expiry_narrative(self, df, days_back=3):
        """
        Generates a narrative string for the top expiry.
        """
        if df.empty: return "No data available."
        
        # Filter for last N days
        cutoff = df['date'].max() - timedelta(days=days_back)
        recent_df = df[df['date'] >= cutoff]
        
        if recent_df.empty: return "No recent data."
        
        # Group by Expiry
        # Calculate Net Flow (Bull - Bear)
        # We need 'is_bull' and 'premium'
        
        # Mocking the aggregation for the test
        # Assume df has 'expiry', 'premium', 'is_bull'
        
        exp_stats = recent_df.groupby('expiry').apply(
            lambda x: pd.Series({
                'net_flow': x[x['is_bull']]['premium'].sum() - x[~x['is_bull']]['premium'].sum(),
                'total_vol': x['premium'].sum()
            })
        ).reset_index()
        
        exp_stats.sort_values('total_vol', ascending=False, inplace=True)
        
        if exp_stats.empty: return "No active expirations."
        
        top_exp = exp_stats.iloc[0]
        expiry = top_exp['expiry']
        net_flow = top_exp['net_flow']
        
        flow_type = "Bullish" if net_flow > 0 else "Bearish"
        
        return f"Over the last {days_back} days, ${abs(net_flow):,.0f} of {flow_type} flow has rotated into the {expiry} Expiry."

class TestSnapshotLogic(unittest.TestCase):
    def setUp(self):
        self.logic = SnapshotLogic()

    def test_vwap_calculation(self):
        print("\n--- TEST: VWAP Calculation ---")
        # Case: 100 contracts @ $2.00 ($200 premium? No, premium is total val)
        # If Premium = $20,000 and Vol = 100
        # VWAP = 20000 / 100 = 200 (Price per share? Or contract?)
        # Usually option price is per share, so / 100?
        # The user said: "VWAP is calculated as Total_Premium_Sum / Total_Volume_Sum"
        # Let's stick to that formula.
        
        prem = 8100000 # $8.1M
        vol = 1000     # 1000 contracts
        # VWAP = 8100
        
        vwap = self.logic.calculate_vwap(prem, vol)
        print(f"Premium: {prem}, Vol: {vol} -> VWAP: {vwap}")
        self.assertEqual(vwap, 8100.0)
        
        # User complained about "Astronomical numbers like $81,000".
        # If Premium is total dollar value ($8.1M) and Volume is contracts (1000).
        # Then 8100 is the price per contract.
        # Price per share would be 81.00.
        # Maybe the user wants price per share? 
        # "Whale's breakeven price" usually refers to the option price (e.g., $5.50).
        # If so, we should divide by 100 if the volume is in contracts.
        # BUT, the user explicitly said: "Ensure VWAP is calculated as Total_Premium_Sum / Total_Volume_Sum".
        # If I follow that literally, I get price per contract.
        # I will stick to the literal formula but keep in mind the "Astronomical" complaint.
        # If the result is 81000, that means Premium was huge relative to Volume.

    def test_spot_price_scaling(self):
        print("\n--- TEST: Spot Price Scaling ---")
        # SPX Spot at 600 -> Should be 6000
        scaled_spx = self.logic.scale_spot_price("SPX", 600)
        print(f"SPX Input: 600 -> Scaled: {scaled_spx}")
        self.assertEqual(scaled_spx, 6000)
        
        # SPY Spot at 6000 -> Should be 600
        scaled_spy = self.logic.scale_spot_price("SPY", 6000)
        print(f"SPY Input: 6000 -> Scaled: {scaled_spy}")
        self.assertEqual(scaled_spy, 600)

    def test_heatmap_range(self):
        print("\n--- TEST: Heatmap Range ---")
        spot = 6000
        strikes = [5000, 5500, 5900, 6000, 6100, 6500, 7000]
        # +/- 10% of 6000 is 5400 to 6600
        # Expected: 5500, 5900, 6000, 6100, 6500
        
        filtered = self.logic.filter_heatmap_range(strikes, spot)
        print(f"Spot: {spot}, Strikes: {strikes} -> Filtered: {filtered}")
        self.assertEqual(filtered, [5500, 5900, 6000, 6100, 6500])

    def test_narrative_generation(self):
        print("\n--- TEST: Narrative Generation ---")
        # Create dummy DF
        data = {
            'date': [datetime.now(), datetime.now(), datetime.now() - timedelta(days=1)],
            'expiry': ['2025-12-20', '2025-12-20', '2025-11-28'],
            'premium': [1000000, 500000, 200000],
            'is_bull': [True, False, True] # Net for 12-20: 1M - 500k = 500k Bull
        }
        df = pd.DataFrame(data)
        
        narrative = self.logic.generate_expiry_narrative(df)
        print(f"Narrative: {narrative}")
        self.assertIn("Bullish flow", narrative)
        self.assertIn("2025-12-20", narrative)

if __name__ == '__main__':
    unittest.main()
