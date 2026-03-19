import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

# Import NexusEngine
try:
    from ts_nexus import NexusEngine, TradeStationManager, TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID
except ImportError:
    sys.path.append("/Users/haydencscott/Desktop/Local Scripts")
    from ts_nexus import NexusEngine, TradeStationManager, TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID

async def run_test():
    print("--- STARTING SPREAD LOGIC VERIFICATION ---")
    
    # Instantiate Engine
    engine = NexusEngine()
    engine.TS = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID)
    
    # Test Params
    SHORT_SYM = "SPY 250116P665"
    LONG_SYM = "SPY 250116P660"
    QTY = 1
    PRICE = 1.00 # Credit
    STOP_TRIGGER = 662.50 # Underlying Price
    
    print(f"1. Testing EXECUTE_SPREAD (Market Entry + GTC Profit Limit)...")
    
    print(f"1. Testing EXECUTE_SPREAD (Market Entry + GTC Profit Limit)...")
    
    # Fetch Chain to get a valid symbol
    print("DEBUG: Fetching Chain to get valid symbol...")
    chain = await engine.fetch_option_chain("SPY", "665", "5", "PUT")
    if not chain:
        print("ERROR: Could not fetch chain. Aborting.")
        return

    valid_short = chain[0]['short_sym']
    valid_long = chain[0]['long_sym']
    print(f"DEBUG: Got Valid Symbols: {valid_short} / {valid_long}")
    
    # Test Execution with these symbols
    # Try with AssetType: StockOption
    print("DEBUG: Executing with AssetType='StockOption'")
    
    # We need to manually call execute_spread or modify it to accept AssetType override?
    # execute_spread currently hardcodes "Option" (from my last edit).
    # Let's modify execute_spread to accept asset_type kwarg or just change it in ts_nexus.py.
    # Actually, let's just use execute_order (single leg) first with this valid symbol.
    
    print(f"DEBUG: Testing Single Leg with {valid_short}")
    res = await engine.execute_order(valid_short, 1, "LIMIT", "BuyToOpen", 1.0) # AssetType defaults to None in execute_order unless I change it.
    print(f"Single Leg Result: {res}")
    
    # Now try spread
    await engine.execute_spread(valid_short, valid_long, QTY, PRICE, STOP_TRIGGER, order_type="MARKET")
    
    print("\n2. Verifying Background Stop Registration...")
    if SHORT_SYM in engine.oco_registry:
        rule = engine.oco_registry[SHORT_SYM]
        print(f"   [PASS] Rule Registered: {rule}")
        if rule["stop_trigger"] == STOP_TRIGGER:
            print(f"   [PASS] Stop Trigger Correct: {rule['stop_trigger']}")
        else:
            print(f"   [FAIL] Stop Trigger Mismatch: {rule['stop_trigger']}")
    else:
        print("   [FAIL] Rule NOT Registered in OCO Registry")

    print("\n3. Simulating Stop Trigger...")
    # Simulate SPY price hitting stop
    engine.current_spy_price = 662.00 # Below trigger for PUT spread
    
    # Manually trigger check (usually runs in loop)
    # We need to call the logic inside `monitor_risk` or extract it.
    # The logic is inside `monitor_risk` loop.
    # Let's extract the check logic or just verify the registry is correct, 
    # as we can't easily run the infinite loop here.
    
    # We can manually call `close_spread` to test that function too.
    print("   Simulating Close Call...")
    await engine.close_spread(SHORT_SYM, LONG_SYM, QTY)
    
    print("\n--- DEBUG: Testing Stock Order (SPY) ---")
    res = await engine.execute_order("SPY", 1, "MARKET", "BUY")
    print(f"Stock Result: {res}")
    await asyncio.sleep(1)

    print("\n--- DEBUG: Testing Single Leg Symbol Formats ---")
    formats = [
        "SPY 250116P665",
        "SPY 250116P665.0",
        "SPY 250116P00665000",
        "SPY250116P00665000"
    ]
    
    for fmt in formats:
        print(f"Testing: {fmt}")
        # We use execute_order directly
        # Note: execute_order in ts_nexus.py uses "Buy" / "Sell" which might fail for options if "BuyToOpen" is needed.
        # But let's see if we get "INVALID SYMBOL" or "INVALID TRADE ACTION".
        res = await engine.execute_order(fmt, 1, "LIMIT", "BuyToOpen", 1.0)
        print(f"Result: {res}")
        await asyncio.sleep(1)

    print("\n--- VERIFICATION COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(run_test())
