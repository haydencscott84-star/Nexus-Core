import requests
ORATS_API_KEY = "ca456d95-6548-433b-8d19-482a85e13dae" # FAKE KEY DOES NOT WORK

# LET'S GET IT FROM THE REAL CONFIG
import os, sys
sys.path.append("/Users/haydenscott/Desktop/Local Scripts")
try:
    from config import ORATS_API_KEY
except:
    ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY") # The one from test_orats_live.py!

url = "https://api.orats.io/datav2/live/strikes"
params = {
    "token": ORATS_API_KEY.strip(), 
    "ticker": "SPY", 
    "fields": "ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBidPrice,callAskPrice,putBidPrice,putAskPrice"
}

r = requests.get(url, params=params)
data = r.json().get("data", [])
if data:
    item = data[0]
    print("Keys returned:", list(item.keys()))
    print("Sample:", item)
else:
    print("Error:", r.text)
