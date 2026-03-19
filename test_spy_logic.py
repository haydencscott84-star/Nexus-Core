import numpy as np
from collections import deque, defaultdict
import random

# --- 1. Stats Engine (Z-Score) ---
class StatsEngine:
    def __init__(self, window_size=1000):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.mean = 0.0
        self.std = 0.0

    def process(self, value):
        self.history.append(value)
        if len(self.history) < 2: return 0.0
        vals = np.array(self.history)
        self.mean = np.mean(vals)
        self.std = np.std(vals)
        return (value - self.mean) / self.std if self.std > 0 else 0.0

# --- 2. Spread Detector ---
class SpreadDetector:
    def detect(self, trades):
        # Group by timestamp (and potentially size/expiry)
        grouped = defaultdict(list)
        for t in trades:
            grouped[t['time']].append(t)
            
        spreads = []
        for ts, legs in grouped.items():
            if len(legs) == 2:
                l1, l2 = legs[0], legs[1]
                # Check for Vertical Spread
                # Same Expiry, Same Type (Call/Call or Put/Put), Different Strikes, Opposite Sides
                if (l1['exp'] == l2['exp'] and 
                    l1['type'] == l2['type'] and 
                    l1['side'] != l2['side'] and 
                    l1['strike'] != l2['strike']):
                    
                    spread_type = "Vertical Call Spread" if l1['type'] == 'CALL' else "Vertical Put Spread"
                    spreads.append({
                        'type': spread_type,
                        'legs': legs,
                        'time': ts
                    })
        return spreads

# --- TEST RUNNER ---
def run_tests():
    print("=== TEST 1: Z-Score Logic ===")
    engine = StatsEngine()
    
    # Generate 100 random trades (~$50k)
    print("[*] Generating 100 random trades (Mean=$50k, Std=$5k)...")
    for _ in range(100):
        val = random.gauss(50000, 5000)
        engine.process(val)
        
    # Inject Monster Trade ($5M)
    whale_val = 5_000_000
    print(f"[*] Injecting WHALE: ${whale_val:,.2f}")
    z_score = engine.process(whale_val)
    print(f"[RESULT] Whale Z-Score: {z_score:.2f}")
    
    if z_score > 3.0:
        print("[PASS] Z-Score > 3.0 confirmed.")
    else:
        print(f"[FAIL] Z-Score {z_score:.2f} is too low.")
        exit(1)

    print("\n=== TEST 2: Spread Detector ===")
    detector = SpreadDetector()
    
    # Mock Trades
    # Buy $500 Call @ 10:00:01
    # Sell $505 Call @ 10:00:01
    mock_trades = [
        {'time': '10:00:01', 'exp': '2025-12-19', 'type': 'CALL', 'strike': 500, 'side': 'BUY', 'prem': 1000},
        {'time': '10:00:01', 'exp': '2025-12-19', 'type': 'CALL', 'strike': 505, 'side': 'SELL', 'prem': 800}
    ]
    
    print("[*] Analyzing Mock Trades...")
    detected = detector.detect(mock_trades)
    
    if not detected:
        print("[FAIL] No spread detected.")
        exit(1)
        
    for s in detected:
        print(f"[RESULT] Detected: {s['type']} at {s['time']}")
        if s['type'] == "Vertical Call Spread":
            print("[PASS] Vertical Call Spread correctly identified.")
        else:
            print(f"[FAIL] Incorrect spread type: {s['type']}")
            exit(1)

    print("\n[SUMMARY] PASSED")

if __name__ == "__main__":
    run_tests()
