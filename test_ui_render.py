import asyncio, time, json
import pandas as pd
from analyze_snapshots import load_unified_data, analyze_persistence, calculate_market_structure_metrics, calculate_trajectory_logic, check_divergence_logic

async def run_test():
    loop = asyncio.get_event_loop()
    full_df = await loop.run_in_executor(None, load_unified_data, 5, None)
    daily_stats = analyze_persistence(full_df)
    last_spot = 660.0
    
    print("Testing build_market_structure equivalents...")
    t_start = time.time()
    
    # Simulate build_market_structure UI Render
    metrics = calculate_market_structure_metrics(full_df, last_spot)
    last_flow_pain = metrics['flow_pain']
    last_top_gex = metrics['top_gex']
    last_magnet = metrics.get('volume_poc', 0)
    
    top_details = metrics.get('top_gex_details', [])
    if not top_details and not last_top_gex.empty:
         for k, v in last_top_gex.items():
             top_details.append({'strike': k, 'gex': v, 'expiry': 'N/A'})
             
    for item in top_details:
        k = item['strike']
        v = item['gex']
        exp = item['expiry']
        abs_v = abs(v)
        if abs_v >= 1e9: fmt_v = f"${v/1e9:.2f}B"
        else: fmt_v = f"${v/1e6:.1f}M"
        if v > 0:
            tag = "POS GEX (+)"
            desc = f"Magnet/Support (Exp: {exp})"
        else:
            tag = "NEG GEX (-)"
            desc = f"Vol Trigger/Accel (Exp: {exp})"

    print(f"[TIMER] Render built in {time.time()-t_start:.2f}s")
    
if __name__ == "__main__":
    asyncio.run(run_test())
