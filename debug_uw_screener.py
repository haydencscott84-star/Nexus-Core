import aiohttp
import asyncio
import os

UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))

async def check_screener():
    url = f"https://api.unusualwhales.com/api/screener/option-contracts"
    params = {'ticker_symbol': 'SPY', 'min_volume': 100, 'min_dte': 0, 'max_dte': 30}
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    
    print(f"Fetching from {url}...")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as sess:
        async with sess.get(url, params=params, headers=headers) as r:
            if r.status != 200:
                print(f"Error: {r.status}")
                print(await r.text())
                return
            
            data = await r.json()
            items = data.get('data', [])
            print(f"Got {len(items)} items.")
            
            if items:
                first = items[0]
                print("\n--- First Item Keys ---")
                for k, v in first.items():
                    print(f"{k}: {v} (Type: {type(v)})")
                
                print("\n--- Volume/OI Check ---")
                print(f"volume: {first.get('volume')}")
                print(f"vol: {first.get('vol')}")
                print(f"open_interest: {first.get('open_interest')}")
                print(f"oi: {first.get('oi')}")

if __name__ == "__main__":
    asyncio.run(check_screener())
