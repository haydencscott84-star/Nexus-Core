
import math
import os
import aiohttp
import asyncio

# Use standard math instead of numpy/scipy to avoid dependency issues on server
def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))

ORATS_API_KEY = os.getenv("ORATS_API_KEY", os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

async def diagnose_smvvol():
    print("Starting Diagnostic...")
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': 'SPY'}
    
    async with aiohttp.ClientSession() as sess:
        async with sess.get(url, params=params) as r:
            if r.status != 200:
                print(f"Error: {r.status}")
                return
            data = (await r.json()).get('data', [])

    if not data:
        print("ERROR: No data returned")
        return
    
    stock_price = float(data[0].get('stockPrice', 0))
    print(f"Stock Price: ${stock_price:.2f}")
    print("=" * 80)
    
    # Filter for OTM Puts (Strike < Spot) and OTM Calls (Strike > Spot)
    otm_puts = [s for s in data if float(s.get('strike', 0)) < stock_price]
    otm_puts.sort(key=lambda x: float(x['strike']), reverse=True) # Nearest OTM first
    
    print(f"\n{'STRIKE':<10} {'DTE':<6} {'smvVol':<10} {'Delta':<10} {'putMidIv':<10} {'d2':<10} {'P(OTM)':<10}")
    print("-" * 80)
    
    smv_vals = []
    
    for strike in otm_puts[:15]:  # First 15 OTM puts
        k = float(strike.get('strike', 0))
        dte = int(strike.get('dte', 0))
        smv = float(strike.get('smvVol', 0))
        # Call delta is usually positive. Put delta = Call - 1
        call_delta = float(strike.get('delta', 0))
        put_delta_approx = call_delta - 1
        
        put_iv = float(strike.get('putMidIv', 0))
        
        if smv > 0: smv_vals.append(smv)
        
        # Calculate d2 and P(OTM)
        if smv > 0 and dte > 0:
            t = dte / 365.0
            r = 0.05 # Mock risk free
            # d2 = (ln(S/K) + (r + 0.5v^2)t) / v*sqrt(t) -> Standard BS d2
            # Note: Formula for d2 usually has (r + 0.5v^2). User's snippet had (r - 0.5v^2).
            # d1 = ... + 0.5v^2
            # d2 = d1 - v*sqrt(t) = ... - 0.5v^2
            # Let's use standard d2 for Probability S > K (ITM for Call, OTM for Put)
            
            # d2 (Standard): Prob(S_T > K) under Measure? No, N(d2) is prob ITM for Call.
            num = math.log(stock_price / k) + (r - 0.5 * smv**2) * t
            den = smv * math.sqrt(t)
            d2 = num / den
            
            # For OTM Put (Strike < Spot), we want Prob(S_T > K).
            # Since S > K means Put is OTM.
            # So P(OTM Put) = P(S_T > K) = N(d2).
            p_otm = norm_cdf(d2)
        else:
            d2 = 0
            p_otm = 0
            
        print(f"${k:<9.2f} {dte:<6} {smv:<10.4f} {call_delta:<10.4f} {put_iv:<10.4f} {d2:<10.4f} {p_otm:<10.4f}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("-" * 80)
    
    if smv_vals:
        avg = sum(smv_vals) / len(smv_vals)
        print(f"smvVol Range: {min(smv_vals):.4f} to {max(smv_vals):.4f}")
        print(f"smvVol Mean: {avg:.4f}")
        
        if max(smv_vals) > 5.0:
            print("⚠️ WARNING: smvVol appears to be percentage (need /100)")
        elif max(smv_vals) < 0.01:
            print("⚠️ WARNING: smvVol appears too small")
        else:
            print("✅ smvVol appears to be decimal (0.10 = 10%)")

if __name__ == "__main__":
    asyncio.run(diagnose_smvvol())
