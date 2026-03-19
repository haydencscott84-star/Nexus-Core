import orats_connector
import pandas as pd

print("Fetching data from ORATS...")
df = orats_connector.get_live_chain("SPY")

if not df.empty:
    print(f"SUCCESS: Fetched {len(df)} rows.")
    print(df.head())
    print("Columns:", df.columns.tolist())
else:
    print("FAILURE: No data returned.")
