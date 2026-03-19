
import asyncio
import aiohttp
import os
import json
import math
import datetime

# CONFIG
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
TICKER = "SPY"

print(f"--- DEBUG PARSING START: {datetime.datetime.now()} ---")

async def main():
    async with aiohttp.ClientSession() as session:
        url = "https://api.unusualwhales.com/api/screener/option-contracts"
        # Mimic exact params from nexus_oi_book.py (assuming Spot ~691)
        params = {
            'ticker_symbol': TICKER,
            'limit': 2500,
            'order': 'open_interest',
            'order_direction': 'desc',
            'min_dte': 4,
            'max_dte': 30,
            'min_open_interest': 100,
            'min_strike': 650, 
            'max_strike': 730,
            'type': 'put' # TEST PARAM 2
        }
        headers = {'Authorization': f'Bearer {UW_API_KEY}'}
        
        print(f"Requesting: {params}")
        
        async with session.get(url, headers=headers, params=params) as r:
            print(f"Status: {r.status}")
            if r.status == 200:
                data = (await r.json()).get('data', [])
                print(f"Rows: {len(data)}")
                
                accepted = 0
                rejected = 0
                
                for i, c in enumerate(data[:20]):
                    raw_strike = float(c.get('strike') or 0)
                    sym = c.get('option_symbol', 'N/A')
                    
                    # LOGIC FROM NEXUS_OI_BOOK.PY
                    stk = raw_strike
                    if stk == 0 and len(sym) >= 15:
                        try:
                            # OSI Last 8 chars are strike * 1000
                            stk_str = sym[-8:]
                            stk = float(stk_str) / 1000.0
                        except: pass
                        
                    print(f"Row #{i}: Sym={sym} | RawStrike={raw_strike} -> ParsedStrike={stk}")
                    
                    if 650 <= stk <= 730:
                        accepted += 1
                    else:
                        rejected += 1
                        
                print(f"--- SUMMARY ---")
                print(f"Accepted (In Range): {accepted}")
                print(f"Rejected (Out Range): {rejected}")
                if accepted == 0:
                     print("FAIL: No rows accepted by logic.")
                else:
                     print("PASS: Logic works.")

if __name__ == "__main__":
    asyncio.run(main())
