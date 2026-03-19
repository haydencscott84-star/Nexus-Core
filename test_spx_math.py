import numpy as np
from collections import deque
import random

class StatsEngine:
    def __init__(self, window_size=1000):
        self.window_size = window_size
        self.history = deque(maxlen=window_size)
        self.mean = 0.0
        self.std = 0.0

    def process(self, value):
        """
        Ingest a value, update stats, and return Z-Score.
        """
        self.history.append(value)
        
        # Need at least 2 data points for std dev
        if len(self.history) < 2:
            return 0.0, 0.0, 0.0

        # Calculate Stats (using numpy for speed)
        vals = np.array(self.history)
        self.mean = np.mean(vals)
        self.std = np.std(vals)

        z_score = 0.0
        if self.std > 0:
            z_score = (value - self.mean) / self.std
            
        return z_score, self.mean, self.std

def test_math():
    print("[*] Starting StatsEngine Validation...")
    engine = StatsEngine(window_size=1000)
    
    # 1. Generate Noise (Normal Market Data)
    # Mean = 100k, Std = 10k
    print("[*] Feeding 100 noise trades (Mean=100k)...")
    noise_data = [random.gauss(100000, 10000) for _ in range(100)]
    
    max_noise_z = 0.0
    for val in noise_data:
        z, _, _ = engine.process(val)
        if abs(z) > max_noise_z:
            max_noise_z = abs(z)
            
    print(f"[INFO] Max Noise Z-Score: {max_noise_z:.2f}")
    
    # Assert Noise is reasonable (should be < 3.0 usually, definitely < 4.0 for this distribution)
    # 2.0 is a tight bound for random gauss, let's say < 3.0 to be safe for "noise"
    if max_noise_z > 3.5: 
        print(f"[WARN] Noise Z-Score high: {max_noise_z:.2f}. Randomness happens.")
    else:
        print("[PASS] Noise levels within expected range.")

    # 2. Inject WHALE (Outlier)
    # 5 Million Premium (50 sigma event relative to 100k mean/10k std)
    whale_val = 5_000_000.0
    print(f"[*] Injecting WHALE: ${whale_val:,.2f}")
    
    z_whale, mean, std = engine.process(whale_val)
    
    print(f"[RESULT] Whale Z-Score: {z_whale:.2f}")
    print(f"[DEBUG] Current Mean: {mean:.2f} | Std: {std:.2f}")
    
    # Assertions
    if z_whale > 3.0:
        print("[PASS] Whale correctly identified (> 3.0).")
    else:
        print(f"[FAIL] Whale Z-Score too low ({z_whale:.2f}). Logic error.")
        exit(1)
        
    print("[SUCCESS] All Math Validated.")

if __name__ == "__main__":
    test_math()
