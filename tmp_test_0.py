
import sys
import pandas as pd
import numpy as np
sys.path.append('/root')

from analyze_snapshots import load_unified_data, calculate_market_structure_metrics
df = load_unified_data(0)
print(f"Loaded {len(df)} rows.")

spy_df = df[df['ticker'] == 'SPY'].copy()
print(f"SPY rows: {len(spy_df)}")
if not spy_df.empty:
    print(f"Total Gamma: {spy_df['gamma'].sum()}")
    print(f"Latest Date: {spy_df['date'].max()}")
    
spot = spy_df[spy_df['underlying_price'] > 10.0]['underlying_price'].iloc[-1]
metrics = calculate_market_structure_metrics(df, spot)
print(f"Flow Pain: {metrics.get('flow_pain')}")
print(f"Top GEX:\n{metrics.get('top_gex')}")
print(f"Volume POC: {metrics.get('volume_poc')}")
