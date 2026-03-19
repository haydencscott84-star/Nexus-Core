import os
import asyncio
try:
    from tradestation_explorer import TradeStationManager
except ImportError:
    print("CRITICAL: tradestation_explorer.py not found.")
    exit()

# --- CONFIGURATION ---
TS_CLIENT_ID = os.environ.get("TS_CLIENT_ID", "YOUR_TS_CLIENT_ID")
TS_CLIENT_SECRET = os.environ.get("TS_CLIENT_SECRET", "YOUR_TS_CLIENT_SECRET")

async def run_auth():
    print("\n--- TRADESTATION MASTER AUTH ---")
    print("Initializing manager...")
    ts_manager = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET)
    
    print("\nChecking for valid token...")
    # This will trigger the browser login if needed, 
    # or just quietly succeed if a valid token already exists.
    token = await asyncio.to_thread(ts_manager._get_valid_access_token)
    
    if token:
        print("\n✅ SUCCESS! Valid token secured.")
        print("You can now run all your TUI scripts without login interruptions.")
    else:
        print("\n❌ FAILED to secure token.")

if __name__ == "__main__":
    asyncio.run(run_auth())