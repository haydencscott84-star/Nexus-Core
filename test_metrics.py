import asyncio
from analyze_snapshots import load_unified_data, calculate_market_structure_metrics

async def main():
    df = load_unified_data(5)
    print(f"Loaded {len(df)} rows")
    metrics = calculate_market_structure_metrics(df, 670.0)
    print("FLOW PAIN:", metrics.get('flow_pain'))
    print("TOP GEX DETAILS:", metrics.get('top_gex_details'))
    
    spy_df = df[df['ticker'] == 'SPY'].copy()
    if 'date' in spy_df.columns and not spy_df.empty:
        latest_date = spy_df['date'].max()
        spy_df = spy_df[spy_df['date'] == latest_date]
        if 'gamma' in spy_df.columns:
            print("GAMMA SUM:", spy_df['gamma'].sum())
            print("GAMMA COUNT > 0:", (spy_df['gamma'] > 0).sum())
        else:
            print("NO GAMMA COLUMN")
    else:
        print("NO DATE COLUMN OR SPY_DF EMPTY")

asyncio.run(main())
