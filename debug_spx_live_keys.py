import os
import requests

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
url = "https://api.orats.io/datav2/live/strikes"
params = {'token': ORATS_API_KEY, 'ticker': 'SPX'}

r = requests.get(url, params=params)
data = r.json().get('data', [])

if data:
    sample = data[0]
    print(f"Items in Live SPX: {len(data)}")
    print("Keys found in first SPX Live record:")
    for k, v in sample.items():
        if v is not None and str(v) != "0":
            print(f"  {k}: {v}")
    
    print(f"\nGamma keys: {'gamma' in sample}, {'gammaSmooth' in sample}")
    print(f"Call OI keys: {'callOpenInterest' in sample}")
else:
    print(f"No data returned for SPX Live. Status: {r.status_code}")
