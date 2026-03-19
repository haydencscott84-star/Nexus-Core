import pandas as pd
url = 'https://docs.google.com/spreadsheets/d/1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg/export?format=xlsx'
df = pd.read_excel(url, sheet_name='SPY 5-Day Flow Ledger', skiprows=19, nrows=15)
print(df.columns)
print(df.head(2))
