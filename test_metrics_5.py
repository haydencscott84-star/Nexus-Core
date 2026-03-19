import pandas as pd
from analyze_snapshots import load_unified_data, calculate_market_structure_metrics

df = load_unified_data(5)
metrics = calculate_market_structure_metrics(df, 670.0)
print(metrics.get("top_gex_details"))
