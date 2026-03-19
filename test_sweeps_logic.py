
import unittest
import pandas as pd
import datetime

# --- LOGIC TO TEST (Copied from V2 for verification) ---

def calculate_aggressor_score(trade):
    """
    Calculates Aggressor Score based on Price vs Bid/Ask.
    Returns: (score, weight)
    """
    price = trade.get('price', 0)
    bid = trade.get('bid', 0)
    ask = trade.get('ask', 0)
    
    # If Bid/Ask missing, fallback to sentiment (Not testing fallback here, assuming data exists)
    if not bid or not ask: return "NEUTRAL", 0.5

    if price >= ask: return "AGGRESSIVE BUY", 1.0
    elif price <= bid: return "PASSIVE SELL", 0.1
    else: return "NEUTRAL", 0.5

def detect_bursts(trades):
    """
    Simulates the burst detection logic.
    Groups trades by (ticker, strike, expiry, type).
    Merges if time delta < 0.5s.
    """
    processed_trades = []
    
    # Sort by time to simulate live feed
    sorted_trades = sorted(trades, key=lambda x: x['executed_at'])
    
    for trade in sorted_trades:
        # Check against last processed trade
        if processed_trades:
            last = processed_trades[-1]
            
            # Key Match
            key_match = (last['ticker'] == trade['ticker'] and 
                         last['strike'] == trade['strike'] and 
                         last['expiry'] == trade['expiry'] and 
                         last['type'] == trade['type'])
            
            # Time Match (< 500ms)
            time_match = abs(trade['executed_at'] - last['executed_at']) < 0.5
            
            if key_match and time_match:
                # MERGE
                last['size'] += trade['size']
                last['premium'] += trade['premium']
                last['is_burst'] = True
                continue # Skip adding this trade as new row
        
        # Add as new trade
        processed_trades.append(trade)
        
    return processed_trades

# --- TEST CASE ---

class TestSweepsLogic(unittest.TestCase):
    def test_aggressor_score(self):
        print("\n--- TEST: Aggressor Score ---")
        
        # 3 Passive Trades (Price <= Bid)
        passive = [
            {'price': 100, 'bid': 100, 'ask': 105},
            {'price': 99, 'bid': 100, 'ask': 105},
            {'price': 100, 'bid': 100, 'ask': 102}
        ]
        
        # 4 Aggressive Trades (Price >= Ask)
        aggressive = [
            {'price': 105, 'bid': 100, 'ask': 105},
            {'price': 106, 'bid': 100, 'ask': 105},
            {'price': 10.5, 'bid': 10.0, 'ask': 10.5},
            {'price': 200, 'bid': 190, 'ask': 200}
        ]
        
        for t in passive:
            tag, w = calculate_aggressor_score(t)
            print(f"Passive Trade: Price={t['price']}, Bid={t['bid']} -> {tag} (Wt={w})")
            self.assertEqual(w, 0.1, "Failed to tag Passive trade correctly")
            
        for t in aggressive:
            tag, w = calculate_aggressor_score(t)
            print(f"Aggressive Trade: Price={t['price']}, Ask={t['ask']} -> {tag} (Wt={w})")
            self.assertEqual(w, 1.0, "Failed to tag Aggressive trade correctly")

    def test_burst_detection(self):
        print("\n--- TEST: Burst Detection ---")
        
        # 4 Trades in 100ms (Burst)
        base_time = 1700000000.0
        burst_trades = [
            {'executed_at': base_time + 0.0, 'ticker': 'SPY', 'strike': 400, 'expiry': '2023-12-01', 'type': 'CALL', 'size': 100, 'premium': 10000},
            {'executed_at': base_time + 0.1, 'ticker': 'SPY', 'strike': 400, 'expiry': '2023-12-01', 'type': 'CALL', 'size': 100, 'premium': 10000},
            {'executed_at': base_time + 0.2, 'ticker': 'SPY', 'strike': 400, 'expiry': '2023-12-01', 'type': 'CALL', 'size': 100, 'premium': 10000},
            {'executed_at': base_time + 0.3, 'ticker': 'SPY', 'strike': 400, 'expiry': '2023-12-01', 'type': 'CALL', 'size': 100, 'premium': 10000},
        ]
        
        # 1 Independent Trade (Different Strike)
        other_trade = [
            {'executed_at': base_time + 0.4, 'ticker': 'SPY', 'strike': 405, 'expiry': '2023-12-01', 'type': 'CALL', 'size': 50, 'premium': 5000}
        ]
        
        all_trades = burst_trades + other_trade
        
        results = detect_bursts(all_trades)
        
        print(f"Input Trades: {len(all_trades)}")
        print(f"Output Events: {len(results)}")
        
        # Should have 2 events: 1 Mega-Sweep (merged 4) + 1 Independent
        self.assertEqual(len(results), 2, "Burst detection failed to merge trades")
        
        mega_sweep = results[0]
        print(f"Mega-Sweep Size: {mega_sweep['size']} (Expected 400)")
        print(f"Mega-Sweep Premium: {mega_sweep['premium']} (Expected 40000)")
        print(f"Is Burst Tag: {mega_sweep.get('is_burst')}")
        
        self.assertEqual(mega_sweep['size'], 400)
        self.assertEqual(mega_sweep['premium'], 40000)
        self.assertTrue(mega_sweep.get('is_burst'), "Failed to tag as Burst")

if __name__ == '__main__':
    unittest.main()
