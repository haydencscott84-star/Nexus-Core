import pandas as pd
import json

url = 'https://docs.google.com/spreadsheets/d/1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg/export?format=xlsx'
df_regime = pd.read_excel(url, sheet_name='Market Regime ', skiprows=1)
df_regime.columns = df_regime.columns.str.strip()

output = {}
if 'Current SPY $' in df_regime.columns:
    output['spy'] = df_regime['Current SPY $'].astype(str).head(5).tolist()
if 'Current SPX $' in df_regime.columns:
    output['spx'] = df_regime['Current SPX $'].astype(str).head(5).tolist()

output['columns'] = list(df_regime.columns)

with open('/tmp/debug_spx.json', 'w') as f:
    json.dump(output, f, indent=2)
