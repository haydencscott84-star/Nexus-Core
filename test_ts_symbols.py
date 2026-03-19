import asyncio
from tradestation_explorer import TradeStationManager, CLIENT_ID, CLIENT_SECRET

async def main():
    ts = TradeStationManager(CLIENT_ID, CLIENT_SECRET, "FILL_ME_IN")
    
    symbols_to_test = ["$VIX.X", "$SPX.X", "@ES", "XLK"]
    
    for sym in symbols_to_test:
        quote = ts.get_quote_snapshot(sym)
        if quote:
            print(f"Requested {sym} -> Received Symbol: {quote.get('Symbol')}")
        else:
            print(f"FAILED: {sym}")

if __name__ == "__main__":
    asyncio.run(main())
