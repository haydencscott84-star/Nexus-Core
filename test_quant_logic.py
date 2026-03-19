
import unittest
import numpy as np

class QuantEngine:
    def __init__(self):
        pass

    def calculate_z_score(self, current_value, history_series):
        """
        Calculates Z-Score using a rolling window of 20 periods.
        Formula: (Current - Mean) / StdDev
        """
        if len(history_series) < 2:
            return 0.0
        
        # Use last 20 items
        window = history_series[-20:]
        mean = np.mean(window)
        std = np.std(window)
        
        if std == 0:
            return 0.0
            
        return (current_value - mean) / std

    def filter_fresh_flow(self, vol, oi):
        """
        Smart Flow Filter:
        - If Volume > Open Interest: Return Volume (High Conviction/Fresh Money)
        - If Volume < Open Interest: Return 0 (Ignore hedging/churn)
        """
        if vol > oi:
            return vol
        return 0

    def check_divergence(self, price_arr, rsi_arr):
        """
        Detects Divergences.
        - Bearish: Price High > Prev High AND RSI High < Prev High
        - Bullish: Price Low < Prev Low AND RSI Low > Prev Low
        
        Assumes arrays are [..., prev, current]
        """
        if len(price_arr) < 3 or len(rsi_arr) < 3:
            return None
            
        # We need at least 2 points to compare (Current vs Previous)
        # But for "Highs" usually we look at local peaks. 
        # The prompt implies simple comparison: "Price High > Previous High"
        # Let's assume the input arrays represent the "Highs" and "Lows" or just "Close" 
        # depending on what we are checking.
        # For this test, we will assume the input arrays ARE the series of Highs (for Bearish) 
        # or Lows (for Bullish).
        
        # Bearish Div Logic (on Highs)
        # Current High > Prev High AND Current RSI < Prev RSI
        curr_price = price_arr[-1]
        prev_price = price_arr[-2]
        curr_rsi = rsi_arr[-1]
        prev_rsi = rsi_arr[-2]
        
        if curr_price > prev_price and curr_rsi < prev_rsi:
            return "BEAR DIV"
            
        # Bullish Div Logic (on Lows) - Note: The prompt asked for specific logic.
        # "Price Low < Previous Low AND RSI Low > Previous Low"
        # We can't check both on the same single array unless we know if it's high or low.
        # However, the prompt says "Detect Bearish... Detect Bullish... Return string".
        # In a real app, we'd pass 'highs' and 'lows'. 
        # For this helper, let's assume we check BOTH conditions on the provided arrays 
        # (which might be 'Close' prices acting as proxy, or we just check the logic requested).
        
        # Let's strictly follow the logic requested for the test:
        # "Price High > Previous High" -> implies we are looking at the last 2 values.
        
        if curr_price < prev_price and curr_rsi > prev_rsi:
            return "BULL DIV"
            
        return None

class TestQuantLogic(unittest.TestCase):
    def setUp(self):
        self.quant = QuantEngine()

    def test_flow_filtering(self):
        print("\n--- TEST: Smart Flow Filter ---")
        # Case A: Vol > OI
        res_a = self.quant.filter_fresh_flow(5000, 1000)
        print(f"Case A (5000 > 1000): {res_a}")
        self.assertEqual(res_a, 5000, "Should return volume if Vol > OI")

        # Case B: Vol < OI
        res_b = self.quant.filter_fresh_flow(200, 5000)
        print(f"Case B (200 < 5000): {res_b}")
        self.assertEqual(res_b, 0, "Should return 0 if Vol < OI")

    def test_z_score(self):
        print("\n--- TEST: Z-Score ---")
        # Create 20 normal numbers
        history = [100000] * 20
        outlier = 5000000 # 5M
        
        z = self.quant.calculate_z_score(outlier, history)
        print(f"History: {history[:3]}... (len={len(history)})")
        print(f"Current: {outlier}")
        print(f"Z-Score: {z}")
        
        # Mean of 20 100k's is 100k. Std is 0. 
        # Wait, if std is 0, we handle it.
        # But let's make the history slightly varied so std != 0 to test the math properly,
        # OR check if the user wanted strictly "normal" (identical) numbers.
        # "100k, 120k" implies variation.
        
        history_varied = [100000, 120000] * 10 # 20 items, mean=110k, std=10k
        z_varied = self.quant.calculate_z_score(outlier, history_varied)
        print(f"Varied Z-Score: {z_varied}")
        
        self.assertTrue(z_varied > 3.0, "Z-Score of outlier should be > 3.0")

    def test_divergence(self):
        print("\n--- TEST: Divergence ---")
        # Bearish Divergence
        # Price Highs: 100, 105, 110 (Higher Highs)
        price_highs = [100, 105, 110]
        # RSI Highs: 70, 65, 60 (Lower Highs)
        rsi_highs = [70, 65, 60]
        
        signal = self.quant.check_divergence(price_highs, rsi_highs)
        print(f"Price: {price_highs}, RSI: {rsi_highs} -> {signal}")
        self.assertEqual(signal, "BEAR DIV")

        # Bullish Divergence
        # Price Lows: 100, 95, 90 (Lower Lows)
        price_lows = [100, 95, 90]
        # RSI Lows: 30, 35, 40 (Higher Lows)
        rsi_lows = [30, 35, 40]
        
        signal_bull = self.quant.check_divergence(price_lows, rsi_lows)
        print(f"Price: {price_lows}, RSI: {rsi_lows} -> {signal_bull}")
        self.assertEqual(signal_bull, "BULL DIV")

if __name__ == '__main__':
    unittest.main()
