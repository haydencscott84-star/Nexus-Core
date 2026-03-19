import asyncio
import aiohttp
import ssl
import json
from tradestation_explorer import TradeStationManager, CLIENT_ID, CLIENT_SECRET

async def main():
    ts = TradeStationManager(CLIENT_ID, CLIENT_SECRET, "FILL_ME_IN")
    
    symbols = ["SPY", "$SPX.X", "$VIX.X", "XLK", "@ES"]
    url = f"{ts.BASE_URL}/marketdata/stream/quotes/{','.join(symbols)}"
    headers = {"Authorization": f"Bearer {ts.access_token}"}
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    
    received_symbols = set()
    
    print(f"Connecting to stream for: {symbols}")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=ssl_ctx)) as s:
        async with s.get(url, headers=headers, timeout=10) as r:
            if r.status == 200:
                print("Stream Connected. Listening for 5 seconds...")
                try:
                    async with asyncio.timeout(5.0):
                        async for line in r.content:
                            if line:
                                d = json.loads(line)
                                if "Symbol" in d:
                                    received_symbols.add(d["Symbol"])
                                    print(f"Tick received for: {d['Symbol']}")
                except asyncio.TimeoutError:
                    print("Listening finished.")
            else:
                print(f"Stream Error: {r.status}")
                print(await r.text())
                
    print(f"Symbols received on stream: {received_symbols}")
    for sym in symbols:
        if sym not in received_symbols:
            print(f"MISSING: {sym}")

if __name__ == "__main__":
    asyncio.run(main())
