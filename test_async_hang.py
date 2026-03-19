import asyncio, time
import pandas as pd
from analyze_snapshots import load_unified_data

async def background_task():
    print("[THREAD] Starting background executor...")
    loop = asyncio.get_event_loop()
    try:
        # Pass a minimal dataframe fetch
        full_df = await loop.run_in_executor(None, load_unified_data, 5, None)
        print(f"[THREAD] Executor returned {len(full_df)} rows.")
    except Exception as e:
        print(f"[THREAD] EXECUTOR CRASH: {e}")

async def main():
    print("[MAIN] Launching background task...")
    task = asyncio.create_task(background_task())
    
    print("[MAIN] Doing UI stuff...")
    for i in range(5):
        print(f"[MAIN] Tick {i}...")
        await asyncio.sleep(0.5)
        
    print("[MAIN] Waiting for background...")
    await task
    print("[MAIN] Done.")

asyncio.run(main())
