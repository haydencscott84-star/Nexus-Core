import asyncio, time, json
import pandas as pd
from analyze_snapshots import load_unified_data, analyze_persistence, calculate_market_structure_metrics, calculate_trajectory_logic, check_divergence_logic

async def run_test():
    print("Starting background history test...")
    
    t0 = time.time()
    loop = asyncio.get_event_loop()
    full_df = await loop.run_in_executor(None, load_unified_data, 5, None)
    print(f"[TIMER] load_unified_data finished in {time.time()-t0:.2f}s")
    
    if full_df.empty:
        print("Empty DF")
        return
        
    t1 = time.time()
    daily_stats = analyze_persistence(full_df)
    print(f"[TIMER] analyze_persistence finished in {time.time()-t1:.2f}s")
    
    t2 = time.time()
    # 3. Calculate Trend Signals
    total_oi_delta = daily_stats['oi_delta'].sum()
    total_prem = full_df['premium'].sum()
    bull_prem = full_df[full_df['is_bull']]['premium'].sum()
    sentiment_score = (bull_prem / total_prem * 100) if total_prem > 0 else 50
    net_flow = full_df[full_df['is_bull']]['premium'].sum() - full_df[~full_df['is_bull']]['premium'].sum()
    
    level_stats = daily_stats.groupby('strike')['oi_delta'].sum().sort_values(ascending=False)
    major_support = level_stats.head(1).index[0] if not level_stats.empty else 0
    major_resistance = level_stats.tail(1).index[0] if not level_stats.empty else 0
    print(f"[TIMER] Metrics Calculation finished in {time.time()-t2:.2f}s")

    t3 = time.time()
    last_spot = 660.0
    struct_metrics = calculate_market_structure_metrics(full_df, last_spot)
    print(f"[TIMER] calculate_market_structure_metrics finished in {time.time()-t3:.2f}s")
    
    t4 = time.time()
    trajectory = calculate_trajectory_logic(last_spot, struct_metrics['flow_pain'], struct_metrics['top_gex'], full_df, struct_metrics.get('volume_poc', 0))
    print(f"[TIMER] calculate_trajectory_logic finished in {time.time()-t4:.2f}s")
    
    t5 = time.time()
    divergence = check_divergence_logic(daily_stats, sentiment_score)
    print(f"[TIMER] check_divergence_logic finished in {time.time()-t5:.2f}s")

if __name__ == "__main__":
    asyncio.run(run_test())
