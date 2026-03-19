import pandas as pd
import streamlit as st

url = 'https://docs.google.com/spreadsheets/d/1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg/export?format=xlsx'
df_spx_vol = pd.read_excel(url, sheet_name='5-Day Flow Ledger', skiprows=1, nrows=15)
df_spx_oi = pd.read_excel(url, sheet_name='5-Day Flow Ledger', skiprows=19, nrows=15)

print(df_spx_vol.columns)
print(df_spx_oi.columns)
