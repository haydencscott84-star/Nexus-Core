
import math
import aiohttp
import asyncio
import os

# Position: SPY 675/670 Put Credit Spread (Bullish)
# Short: 675
# Spot: ~684.12
# Trade is ITM (Winning). We want S > 675 at expiration.
# Expected Win Rate: High (> 50%)

SHORT_STRIKE = 675.0
ORATS_API_KEY = os.getenv("ORATS_API_KEY", os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

def calculate_pop(spot, breakeven, dte, iv, strategy_type='bull'):
    try:
        if dte <= 0: dte = 0.0001
        t = dte / 365.0
        r = 0.0
        
        if iv <= 0: return 0.0
        
        ln_sk = math.log(spot / breakeven)
        drift = (r - 0.5 * iv**2) * t
        vol_term = iv * math.sqrt(t)
        
        d2 = (ln_sk + drift) / vol_term
        
        cdf = 0.5 * (1 + math.erf(d2 / math.sqrt(2)))
        
        # Bull: Profit if Spot > Breakeven
        if strategy_type == 'bull':
            return cdf * 100
        else:
            return (1 - cdf) * 100
    except Exception as e:
        print(f"Calc Error: {e}")
        return 0.0

async def check_put_data():
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    
    print("Fetching 675 Put Data...")
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, params=params) as r:
            data = (await r.json()).get('data', [])
            
            # Find 675
            matches = [x for x in data if float(x['strike']) == SHORT_STRIKE]
            
            if not matches:
                print("No data for 675")
                return

            print(f"Found {len(matches)} expiries for 675.")
            
            # Check a few expiries
            for m in matches[:5]:
                try:
                    dte = int(m.get('dte', 0))
                    smv = float(m.get('smvVol', 0))
                    spot = float(m.get('stockPrice', 0))
                    
                    # Estimate Credit ~ 0.50 for context (675 is OTM Put? No Spot 684. 675 Put is OTM.)
                    # Wait. Spot 684. Put 675. Put is OTM.
                    # Price ~ Low.
                    credit = 0.5
                    be = SHORT_STRIKE - credit # Bull Put
                    
                    # Strategy: Bull (Put Credit)
                    pop = calculate_pop(spot, be, dte, smv, 'bull')
                    
                    print(f"Exp: {m['expirDate']} (DTE {dte}) | smvVol: {smv:.4f} | Spot: {spot} | Win%: {pop:.2f}%")
                except Exception as e:
                    print(f"Error parsing match: {e}")

if __name__ == "__main__":
    asyncio.run(check_put_data())
