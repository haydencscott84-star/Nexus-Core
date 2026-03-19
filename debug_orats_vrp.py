
import asyncio
import aiohttp
import os
import json

# API KEYS (Hardcoded for Test)
ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
TICKER = "SPY"

# [UPDATED] Added fields to optimize payload and include hv30
orats_fields = "ticker,stockPrice,prevClose,iv30d,hv30,impliedVol"

async def test_fetch():
    print(f"Testing ORATS Fetch for {TICKER} with fields={orats_fields}")
    async with aiohttp.ClientSession() as s:
        try:
            url = "https://api.orats.io/datav2/live/summaries"
            params = {'token': ORATS_API_KEY, 'ticker': TICKER, 'fields': orats_fields}
            print(f"GET {url} {params}")
            
            async with s.get(url, params=params, timeout=10) as r:
                print(f"Status: {r.status}")
                if r.status == 200:
                    data = await r.json()
                    # print(f"Raw Response: {json.dumps(data, indent=2)}")
                    
                    d_list = data.get('data', [])
                    if d_list:
                        d = d_list[0]
                        print(f"KEYS: {list(d.keys())}")
                        iv30 = float(d.get('iv30d') or 0)
                        hv30_candidate = float(d.get('rVol30') or 0)
                        print(f"Parsed -> IV30: {iv30}, rVol30 (HV30?): {hv30_candidate}")
                    else:
                        print("❌ No 'data' list in response")
                else:
                    text = await r.text()
                    print(f"❌ Error Response: {text}")
                    
        except Exception as e:
            print(f"❌ Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_fetch())
