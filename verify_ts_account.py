import asyncio
import os
import sys

# Ensure local imports work
sys.path.append(os.getcwd())

from tradestation_explorer import TradeStationManager
from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID

FUTURES_ACCOUNT_ID = "210VGM01"

async def test_account_access():
    print(f"--- Verifying Access for Account: {FUTURES_ACCOUNT_ID} ---")
    
    # Pass credentials explicitly
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
    
    # 1. Check if we can get an Access Token (this handles refresh if needed)
    print("1. Acquiring Token...")
    token = ts.access_token
    if not token:
        print("❌ FAILED: Could not get access token.")
        return

    print(f"✅ Token Acquired (Starts with: {token[:10]}...)")

    # 2. Try to fetch positions for this specific account
    print(f"2. Fetching Positions for {FUTURES_ACCOUNT_ID}...")
    try:
        positions = ts.get_positions(account_id=FUTURES_ACCOUNT_ID)
        print(f"✅ API Call Successful.")
        print(f"   Positions Found: {len(positions)}")
        print(f"   Raw Data: {positions}")
    except Exception as e:
        print(f"❌ API Call FAILED: {e}")

if __name__ == "__main__":
    asyncio.run(test_account_access())
