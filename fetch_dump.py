import os
import json
import requests

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY") # Valid API Key Used on Staging
url = "https://api.orats.io/datav2/live/strikes"
params = {
    "token": ORATS_API_KEY.strip(), 
    "ticker": "SPY", 
    "fields": "ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBidPrice,callAskPrice,putBidPrice,putAskPrice"
}

print("Fetching data from ORATS...")
r = requests.get(url, params=params)
data = r.json()

with open("local_orats_dump.json", "w") as f:
    json.dump(data, f)
print("Saved to local_orats_dump.json")
