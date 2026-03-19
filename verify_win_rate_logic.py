
import math
import aiohttp
import asyncio
import os

# Mock Inputs based on User Request
# Position: SPY 675/705 Debit Call Spread
LONG_STRIKE = 675.0
SHORT_STRIKE = 705.0
WIDTH = 30.0
DTE = 48
SPOT_PRICE = 685.84 # From screenshot
ORATS_API_KEY = os.getenv("ORATS_API_KEY", "")

def calculate_pop(spot, breakeven, dte, iv, strategy_type='bull'):
    try:
        if dte <= 0: dte = 0.0001
        t = dte / 365.0
        r = 0.0  # Risk free rate
        
        if iv <= 0: return 0.0
        
        ln_sk = math.log(spot / breakeven)
        drift = (r - 0.5 * iv**2) * t
        vol_term = iv * math.sqrt(t)
        
        d2 = (ln_sk + drift) / vol_term
        
        cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        
        print(f"  [CALC DEBUG] Spot={spot}, BE={breakeven:.2f}, IV={iv}, T={t:.4f}, D2={d2:.4f}, CDF={cdf:.4f}")

        if strategy_type == 'bull':
            return cdf * 100
        else:
            return (1 - cdf) * 100
    except Exception as e:
        print(f"Calc Error: {e}")
        return 0.0

async def verify_logic():
    print(f"--- Verifying Win% Logic for SPY {LONG_STRIKE}/{SHORT_STRIKE} Debit Call ({DTE} DTE) ---")
    print(f"Spot Price: {SPOT_PRICE}")

    # 1. Fetch IV from ORATS
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    
    iv_found = 0.0
    
    print("Fetching ORATS Data...")
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, params=params) as r:
            if r.status != 200:
                print(f"API Error: {r.status} {await r.text()}")
                return
            
            data = (await r.json()).get('data', [])
            print(f"Received {len(data)} rows.")
            
            # Find closest expiry to 48 DTE
            # We don't have exact date in script, so we look for DTE match approx
            # In live app, it matches by Expiry Date string. 
            # For this test, verifying the KEY format is crucial.
            
            target_key_float = f"|{LONG_STRIKE:.1f}"
            target_key_int = f"|{int(LONG_STRIKE)}"
            
            # Search for the specific strike
            matches = []
            for i in data:
                # Mock finding the right expiry (assuming one matches ~48 dte or we pick one)
                # In this test, we just look for the strike to get ANY valid IV for that strike
                strike_val = float(i['strike'])
                if strike_val == LONG_STRIKE:
                    # PRIORITIZE SMOOTHED VOLATILITY (smvVol)
                    iv = float(i.get('smvVol', i.get('impliedVolatility', i.get('iv', 0))))
                    print(f"Strike: {strike_val} | smvVol: {i.get('smvVol')} | Raw: {i.get('iv')}")
                    
                    dte_val = i.get('dte', 0) 
                    matches.append((i['expirDate'], iv))

    if not matches:
        print("CRITICAL: No data found for strike 675.0 in ORATS response.")
    else:
        print(f"Found {len(matches)} expiries for Strike {LONG_STRIKE}.")
        # Pick one to test calc
        # Let's assume we found the one for 2026-02-20 (from screenshot)
        test_iv = matches[0][1] # Use first found IV
        print(f"Using Test IV: {test_iv}")
        
        # 2. Derive Breakeven (Approximate)
        # Debit = ~16.60 (from screenshot logic for similar strikes, middle of chain)
        # Actually let's calculated based on width/delta. 
        # From screenshot: Debit $16.60.
        debit = 16.60
        be = LONG_STRIKE + debit
        print(f"Derived Stats: Debit={debit}, BreakEven={be}")
        
        # 3. Run Calculation
        win_rate = calculate_pop(SPOT_PRICE, be, DTE, test_iv, 'bull')
        print(f"Calculated Win Rate: {win_rate:.2f}%")

if __name__ == "__main__":
    if not ORATS_API_KEY:
        print("Error: ORATS_API_KEY not set")
    else:
        asyncio.run(verify_logic())
