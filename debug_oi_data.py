
import asyncio
import aiohttp
import os
import json
import math
import datetime

# CONFIG
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"

async def main():
    print(f"--- DEBUG START: {datetime.datetime.now()} ---")
    async with aiohttp.ClientSession() as session:
        # 1. FETCH SPOT
        print("[1] Fetching Spot/IV from ORATS...")
        current_spot = 0.0
        implied_move = 0.0
        
        try:
            url = "https://api.orats.io/datav2/live/summaries"
            params = {'token': ORATS_API_KEY, 'ticker': TICKER}
            async with session.get(url, params=params, timeout=10) as r:
                print(f"    ORATS Status: {r.status}")
                if r.status == 200:
                    data = (await r.json()).get('data', [{}])[0]
                    current_spot = float(data.get('stockPrice', 0))
                    iv30 = float(data.get('iv30d', 0))
                    print(f"    Spot: {current_spot}, IV30: {iv30}")
                    
                    if current_spot > 0 and iv30 > 0:
                        implied_move = current_spot * iv30 * math.sqrt(30.0 / 365.0)
                        print(f"    Implied Move: +/- {implied_move:.2f}")
        except Exception as e:
            print(f"    ERROR fetching Spot: {e}")

        # 2. CALC PARAMS
        print("\n[2] Calculating API Params...")
        min_strike = 0
        max_strike = 0
        if current_spot > 0:
            if implied_move > 0:
                min_strike = int(current_spot - (implied_move * 1.5))
                max_strike = int(current_spot + (implied_move * 1.5))
            else:
                min_strike = int(current_spot * 0.88)
                max_strike = int(current_spot * 1.12)
            print(f"    Target Strike Range: {min_strike} - {max_strike}")
        else:
            print("    CRITICAL: No Spot Price. Will use default/global fetch (prone to junk).")

        # 3. FETCH UW
        print("\n[3] Fetching UW Data (Swing Bucket: 4-30d)...")
        url = "https://api.unusualwhales.com/api/screener/option-contracts"
        api_params = {
            'ticker_symbol': TICKER,
            'limit': 2500,
            'order': 'open_interest',
            'order_direction': 'desc',
            'min_dte': 4,
            'max_dte': 30,
            'min_open_interest': 100
        }
        if min_strike > 0:
            api_params['min_strike'] = min_strike
            api_params['max_strike'] = max_strike
            
        print(f"    Request Params: {api_params}")
        
        try:
            headers = {'Authorization': f'Bearer {UW_API_KEY}'}
            async with session.get(url, headers=headers, params=api_params, timeout=15) as r:
                print(f"    UW Status: {r.status}")
                if r.status == 200:
                    contracts = (await r.json()).get('data', [])
                    print(f"    Contracts Returned: {len(contracts)}")
                    
                    # 4. ANALYZE DATA
                    print("\n[4] Sampling Data:")
                    valid_count = 0
                    for i, c in enumerate(contracts[:10]):
                        strike = float(c.get('strike', 0))
                        sym = c.get('option_symbol', 'N/A')
                        oi = int(c.get('open_interest', 0))
                        print(f"    #{i+1}: {sym} | Strike: {strike} | OI: {oi}")
                        
                        if min_strike <= strike <= max_strike:
                            valid_count += 1
                            
                    print(f"\n[5] Analysis:")
                    print(f"    Total in Response: {len(contracts)}")
                    print(f"    Visible in Range ({min_strike}-{max_strike}): {valid_count} (in top 10)")
                    
                    if len(contracts) == 0:
                         print("    FAILURE: API returned 0 rows.")
                    elif valid_count == 0:
                         print("    FAILURE: Rows returned but ALL are outside range (API ignored params?)")
                    else:
                         print("    SUCCESS: Valid data found.")
                         
                else:
                    print(f"    API Error: {await r.text()}")
        except Exception as e:
            print(f"    Exception: {e}")

if __name__ == "__main__":
    asyncio.run(main())
