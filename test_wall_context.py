import time
import pandas as pd
import numpy as np

print("Generating simulated 40k strike rows for Wall Context loop...")
df = pd.DataFrame({
    'ticker': np.random.choice(['SPX', 'SPY'], 40000),
    'strike': np.random.randint(400, 700, 40000),
    'expiry': ['2026-03-20'] * 40000,
    'notional_delta': np.random.uniform(-1e6, 1e6, 40000),
    'oi': np.random.randint(0, 1000, 40000),
    'delta': np.random.uniform(-1, 1, 40000)
})

# Add verified chain mock data
verified_chain_agg = {str(k): float(v) for k, v in zip(np.random.randint(400, 700, 1000), np.random.uniform(-1e6, 1e6, 1000))}
valid_walls = {}
SPX_PRICE, SPY_PRICE = 6900.0, 690.0

start_time = time.time()
print("Executing iterrows() loop (Line 1681)...")

for tick in ["SPX", "SPY"]:
    valid_walls[tick] = {}
    subset = df[df['ticker'] == tick]
    
    # Group by Strike
    agg_subset = subset.groupby('strike')['notional_delta'].sum().reset_index()
    
    for _, row in agg_subset.iterrows():
        k = str(float(row['strike']))
        n_delta = row['notional_delta']

        if tick == "SPX" and k in verified_chain_agg:
            n_delta = verified_chain_agg[k]
        
        valid_walls[tick][k] = {
            "delta": n_delta,
            "oi_delta": 0, 
            "status": "ACTIVE" 
        }

print(f"DONE in {time.time() - start_time:.2f}s")
