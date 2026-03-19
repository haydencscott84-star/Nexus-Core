import asyncio
from analyze_snapshots import load_unified_data

df = load_unified_data(5)
spy_df = df[df['ticker'] == 'SPY'].copy()
if 'date' in spy_df.columns and not spy_df.empty:
    latest_date = spy_df['date'].max()
    print(f"LATEST DATE: {latest_date}")
    spy_df = spy_df[spy_df['date'] == latest_date]
    print(f"ROWS FOR LATEST DATE: {len(spy_df)}")
    
    # Check what columns are there
    print(spy_df[['strike', 'type', 'gamma']].head(10))
