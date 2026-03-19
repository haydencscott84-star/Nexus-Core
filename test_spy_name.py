import pandas as pd
url = 'https://docs.google.com/spreadsheets/d/1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg/export?format=xlsx'
df = pd.read_excel(url, sheet_name='Market Regime ', skiprows=1)
df.columns = df.columns.str.strip()
print([c for c in df.columns if 'SPY' in c])
print([c for c in df.columns if 'SPX' in c])
