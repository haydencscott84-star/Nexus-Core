import pandas as pd
import glob
files = sorted(glob.glob("/root/snapshots_spy/*.csv"))
f = files[-1]
print("Loading:", f)
df = pd.read_csv(f)
print("Delta value counts:\n", df['delta'].value_counts())
print("Vega value counts:\n", df['vega'].value_counts())
print("Theta value counts:\n", df['theta'].value_counts())
print("Vol value counts:\n", df['vol'].value_counts())
