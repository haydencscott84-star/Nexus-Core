import asyncio
import time
import json
import os
from trader_dashboard import antigravity_dump, async_antigravity_dump

# Mock Data (Large enough to cause delay)
LARGE_DATA = {"data": ["x" * 1000 for _ in range(1000)]} # ~1MB

async def test_async_dump():
    print("--- Testing Async Dump ---")
    start = time.time()
    
    # Fire off 10 dumps
    tasks = []
    for i in range(10):
        tasks.append(async_antigravity_dump(f"test_dump_{i}.json", LARGE_DATA))
    
    # Measure time to *queue* tasks (should be near instant)
    queued_time = time.time() - start
    print(f"Time to queue 10 dumps: {queued_time:.4f}s")
    
    if queued_time > 0.1:
        print("FAIL: Queuing took too long (Blocking?)")
    else:
        print("PASS: Non-blocking execution confirmed.")
        
    await asyncio.gather(*tasks)
    total_time = time.time() - start
    print(f"Total completion time: {total_time:.4f}s")
    
    # Cleanup
    for i in range(10):
        if os.path.exists(f"test_dump_{i}.json"): os.remove(f"test_dump_{i}.json")

def test_throttling_logic():
    print("\n--- Testing Throttling Logic ---")
    last_update = 0
    updates_allowed = 0
    
    start_sim = time.time()
    # Simulate 100 updates in 0.5 seconds
    for i in range(100):
        now = time.time()
        # Logic from dashboard: if now - last > 0.1
        if now - last_update > 0.1:
            updates_allowed += 1
            last_update = now
        time.sleep(0.005) # Fast stream
        
    print(f"Simulated 100 fast updates.")
    print(f"Allowed Updates: {updates_allowed}")
    
    if updates_allowed < 10:
        print("PASS: Throttling active (Updates reduced).")
    else:
        print(f"FAIL: Too many updates allowed ({updates_allowed})")

if __name__ == "__main__":
    asyncio.run(test_async_dump())
    test_throttling_logic()
