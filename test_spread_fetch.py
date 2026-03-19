import asyncio
import sys
import os

# Add current directory to path
sys.path.append(os.getcwd())

# Import NexusEngine
# We need to mock or handle the singleton lock if it's annoying, but it should be fine.
try:
    from ts_nexus import NexusEngine, TradeStationManager, TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID
except ImportError:
    # If running from a different dir, try adding path
    sys.path.append("/Users/haydencscott/Desktop/Local Scripts")
    from ts_nexus import NexusEngine, TradeStationManager, TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID

async def run_test():
    print("--- STARTING LIVE SPREAD SNIPER TEST ---")
    
    # Instantiate Engine
    engine = NexusEngine()
    
    # Manually init TS Manager (NexusEngine does it in start_workers usually)
    print("Authenticating with TradeStation...")
    engine.TS = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID)
    
    # Test Parameters
    TICKER = "SPY"
    STRIKE = "665"
    WIDTH = "5"
    TYPE = "PUT"
    
    print(f"Fetching Option Chain for: {TICKER} {TYPE} Spread (Short: {STRIKE}, Width: {WIDTH})...")
    
    # Call the method directly
    results = await engine.fetch_option_chain(TICKER, STRIKE, WIDTH, TYPE)
    
    print(f"\nFound {len(results)} Expirations/Spreads:\n")
    
    # Print Table Header
    print(f"{'EXPIRY':<12} {'DTE':<5} {'SHORT':<8} {'LONG':<8} {'CREDIT':<8} {'RISK':<8} {'R/R':<6} {'BREAKEVEN':<10}")
    print("-" * 80)
    
    for r in results:
        print(f"{r['expiry']:<12} {r['dte']:<5} {r['short']:<8} {r['long']:<8} ${r['credit']:<7} ${r['risk']:<7} {r['rr']:<5}% ${r['breakeven']:<9}")
        
    print("\n--- TEST COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(run_test())
