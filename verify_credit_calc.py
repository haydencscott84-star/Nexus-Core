
import math
import aiohttp
import asyncio
import os

# Position: SPY 705/710 Credit Call Spread (Bearish)
# Short: 705
# Long: 710
# DTE: 27
# Spot: ~686
# Credit: Estimate ~1.00 (Width 5, ~20 delta maybe?)

SHORT_STRIKE = 705.0
LONG_STRIKE = 710.0
DTE = 27
ORATS_API_KEY = os.getenv("ORATS_API_KEY", "")

def calculate_pop(spot, breakeven, dte, iv, strategy_type='bull'):
    try:
        print(f"DEBUG INPUTS: Spot={spot} BE={breakeven} DTE={dte} IV={iv} Type={strategy_type}")
        if dte <= 0: dte = 0.0001
        t = dte / 365.0
        r = 0.0
        
        if iv <= 0: 
            print("ERROR: IV is 0")
            return 0.0
        
        ln_sk = math.log(spot / breakeven)
        drift = (r - 0.5 * iv**2) * t
        vol_term = iv * math.sqrt(t)
        
        d2 = (ln_sk + drift) / vol_term
        
        cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        
        print(f"DEBUG CALC: t={t:.4f} ln_sk={ln_sk:.4f} d2={d2:.4f} CDF={cdf:.4f}")

        if strategy_type == 'bull':
            res = cdf * 100
        else:
            # Bear: Probability Spot < Breakeven
            # If Spot < Breakeven, ln(S/K) is negative.
            # d2 is negative. CDF is small (e.g. 0.3).
            # We want Probability of STAYING below.
            # Normal CDF(d2) is prob S_t < K (Risk Neutral measure N(d2) corresponds to exercise prob?)
            # Actually N(d2) is probability S_T > K in BS call formula?
            # Standard N(d2) is probability Call expires ITM (S > K).
            # So for Bear Call, we want Prob(S < K) = 1 - N(d2).
            res = (1 - cdf) * 100
            
        print(f"DEBUG RESULT: {res}%")
        return res
    except Exception as e:
        print(f"Calc Error: {e}")
        return 0.0

async def perform_check():
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    
    print("Fetching 705 Strike Data...")
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, params=params) as r:
            data = (await r.json()).get('data', [])
            
            # Find 705
            target_strike = SHORT_STRIKE
            matches = [x for x in data if float(x['strike']) == target_strike]
            
            if not matches:
                print("No data for 705")
                return

            # Pick closest DTE to 27 or use actual
            # Sort by DTE diff
            matches.sort(key=lambda x: abs(int(x.get('dte', 0)) - DTE))
            
            best = matches[0]
            print(f"Selected Expiry: {best['expirDate']} (DTE {best.get('dte')})")
            
            smv_vol = float(best.get('smvVol', 0))
            spot = float(best.get('stockPrice', 685.0))
            
            print(f"Spot: {spot}, smvVol: {smv_vol}")
            
            # Estimate Credit (Mid Price)
            # Call Credit Spread = Short Call - Long Call
            # We need Long Leg too
            long_matches = [x for x in data if float(x['strike']) == LONG_STRIKE and x['expirDate'] == best['expirDate']]
            if long_matches:
                l_leg = long_matches[0]
                # Price approximation using callValue (Theo) or MidIv? Use Call Value
                short_price = float(best.get('callValue', 0))
                long_price = float(l_leg.get('callValue', 0))
                credit = short_price - long_price
                if credit < 0: credit = 0.5 # fallback
            else:
                credit = 1.0 # fallback
                
            print(f"Estimated Credit: {credit:.2f}")
            
            be = SHORT_STRIKE + credit 
            
            win_rate = calculate_pop(spot, be, float(best.get('dte', DTE)), smv_vol, 'bear')
            print(f"---> WIN RATE: {win_rate:.2f}%")

if __name__ == "__main__":
    if not ORATS_API_KEY:
        print("Need API Key")
    else:
        asyncio.run(perform_check())
