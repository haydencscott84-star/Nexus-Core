
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
sys.path.append('/root')

try:
    from analyze_snapshots import load_unified_data, calculate_market_structure_metrics
    print("Loaded analyze_snapshots")
    df = load_unified_data(5)
    print(f"Loaded {len(df)} rows from 5 days.")
    
    spy_df = df[df['ticker'] == 'SPY'].copy()
    spot = spy_df[spy_df['underlying_price'] > 10.0]['underlying_price'].iloc[-1]
    print(f"SPY Spot: {spot}")
    
    metrics = calculate_market_structure_metrics(df, spot)
    print(f"Metrics Output: {metrics}")
except Exception as e:
    print(f"Error: {e}")
