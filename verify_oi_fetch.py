
import asyncio
import aiohttp
import os
import json
import datetime
import math

UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"

print(f"DEBUG: Starting Fetch Test at {datetime.datetime.now()}")

async def fetch_contracts(session, min_dte, max_dte):
    url = "https://api.unusualwhales.com/api/screener/option-contracts"
    params = {
        'ticker_symbol': TICKER,
        'limit': 2500, # Test Production Scale
        'order': 'open_interest',
        'order_direction': 'desc',
        'min_dte': min_dte,
        'min_strike': 660,
        'max_strike': 720,
        'max_dte': max_dte,
        'min_open_interest': 100
    }
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    try:
        print(f"DEBUG: Requesting DTE {min_dte}-{max_dte}...")
        async with session.get(url, headers=headers, params=params, timeout=15) as r:
            print(f"DEBUG: Response {min_dte}-{max_dte}: {r.status}")
            if r.status == 200:
                data = (await r.json()).get('data', [])
                print(f"DEBUG: Got {len(data)} rows.")
                return data
            else:
                print(f"DEBUG: Error Content: {await r.text()}")
    except Exception as e:
        print(f"DEBUG: Exception {min_dte}-{max_dte}: {e}")
    return []

async def main():
    async with aiohttp.ClientSession() as session:
        print("DEBUG: Session Created. Launching tasks...")
        tasks = [
            fetch_contracts(session, 0, 3),   # Short
            fetch_contracts(session, 4, 30),  # Med
            fetch_contracts(session, 31, 720) # Long
        ]
        results = await asyncio.gather(*tasks)
        print("DEBUG: All tasks done.")
        
if __name__ == "__main__":
    asyncio.run(main())
