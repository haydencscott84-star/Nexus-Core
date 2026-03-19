import pandas as pd
import datetime

# Create mock data
data = {'Expiration': ['2026-03-15', 'invalid_date', '2026-03-10']}
df = pd.DataFrame(data)
df['Expiration'] = pd.to_datetime(df['Expiration'], format='mixed', errors='coerce')
print("Dates:", df['Expiration'].dt.date)

latest_trade_date = datetime.date(2026, 3, 14)
try:
    print("Testing filter...")
    mask = df['Expiration'].dt.date > latest_trade_date
    print(mask)
    filtered = df[mask]
    print(filtered)
except Exception as e:
    print(f"ERROR: {type(e).__name__} - {e}")
