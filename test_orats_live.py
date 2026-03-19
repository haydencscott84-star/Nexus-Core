import os
import requests

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")

url = "https://api.orats.io/datav2/live/strikes"
params = {
    'token': ORATS_API_KEY, 
    'ticker': 'SPY',
    'fields': 'ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBidPrice,callAskPrice,putBidPrice,putAskPrice'
}
r = requests.get(url, params=params)
data = r.json()
res = data.get('data', data)
if res:
    print(f"Loaded {len(res)} items")
    print("Sample keys:", res[0].keys())
    print("Sample data:", {k: res[0][k] for k in ['ticker', 'expirDate', 'strike', 'dte'] if k in res[0]})
else:
    print("No data")
