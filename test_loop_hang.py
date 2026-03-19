import pandas as pd
import numpy as np
import time

print("Building dummy 200k dataset...")
df = pd.DataFrame({
    'strike': np.random.randint(400, 700, 200000),
    'type': np.random.choice(['CALL', 'PUT'], 200000),
    'vol': np.random.randint(1, 100, 200000)
})

print("Testing Flow Pain Calc (Line 1901)...")
start = time.time()
strikes = sorted(df['strike'].unique())
pain_map = {}

calls = df[df['type'] == 'CALL']
puts = df[df['type'] == 'PUT']

print(f"Unique Strikes: {len(strikes)}")
for i, k in enumerate(strikes):
    if i % 50 == 0: print(f"Processing strike {i}/{len(strikes)}... Time: {time.time()-start:.2f}s")
    call_val = (k - calls['strike']).clip(lower=0) * calls['vol']
    put_val = (puts['strike'] - k).clip(lower=0) * puts['vol']
    pain_map[k] = call_val.sum() + put_val.sum()

print(f"DONE in {time.time() - start:.2f}s")
