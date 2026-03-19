import json
import pandas as pd

def calc_agg_magnet(master_orats, price):
    try:
        print("Creating DataFrame...")
        orats_df = pd.DataFrame(master_orats)
        print("Checking empty...")
        if orats_df.empty: return pd.Series(dtype=float)
        print("Converting to numeric...")
        cols = ['gamma', 'callOpenInterest', 'putOpenInterest', 'strike']
        for c in cols: orats_df[c] = pd.to_numeric(orats_df[c], errors='coerce').fillna(0)
        print("Calculating total_gamma_exp...")
        orats_df['total_gamma_exp'] = (orats_df['callOpenInterest'] - orats_df['putOpenInterest']) * orats_df['gamma'] * 100 * (price**2) * 0.01
        print("Grouping and sorting...")
        return orats_df.groupby('strike')['total_gamma_exp'].sum().abs().nlargest(1)
    except Exception as e:
        print(f"Exception: {e}")
        return pd.Series(dtype=float)

print("Loading data...")
with open("nexus_gex_static.json", "r") as f:
    master_orats = json.load(f) # Wait, nexus_gex_static.json is just the summarized gex_profiles, NOT master_orats.
    
print("Done")
