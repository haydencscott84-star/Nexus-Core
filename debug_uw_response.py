
import aiohttp
import asyncio
import json
import os
import sys

# Hardcoded key from spx_profiler_nexus.py
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")

import ssl

async def debug_uw():
    print(f"🔑 Using UW Key: {UW_API_KEY[:5]}...")
    url = "https://api.unusualwhales.com/api/screener/option-contracts"
    params = {
        'ticker_symbol': 'SPXW', # Using SPXW as in the main script
        'limit': 1,
        'order': 'premium',
        'order_direction': 'desc'
    }
    
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    
    # Disable SSL Check
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    print(f"🚀 Fetching SPXW data from {url}...")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as session:
        async with session.get(url, headers=headers, params=params) as r:
            if r.status == 200:
                data = await r.json()
                items = data.get('data', [])
                if items:
                    print("\n✅ RECEIVED DATA ITEM:")
                    print(json.dumps(items[0], indent=2))
                else:
                    print("\n⚠️ Success but NO DATA returned.")
            else:
                print(f"\n❌ API ERROR: {r.status}")
                print(await r.text())

if __name__ == "__main__":
    asyncio.run(debug_uw())
