import pandas as pd
from datetime import datetime, timedelta

# Mock the structure of the loaded dataframe based on valid file observation
data = {
    'ticker': ['SPY', 'SPY'],
    'exp': ['', ''], # Empty expiry as seen in file
    'dte': [1, 5],
    'strike': [500, 505],
    'type': ['CALL', 'PUT'],
    'premium': [1000, 2000],
    'vol': [10, 20],
    'oi': [100, 200],
    'date': [datetime(2025, 12, 3).date(), datetime(2025, 12, 3).date()] # Mock loaded date
}

df = pd.DataFrame(data)

print("--- ORIGINAL DATAFRAME ---")
print(df)

# Logic from analyze_snapshots.py
print("\n--- APPLYING LOGIC ---")
df['expiry_dt'] = pd.to_datetime(df['exp'], errors='coerce')
print("Expiry DT Column:")
print(df['expiry_dt'])

today_ts = pd.Timestamp(datetime.now().date())
print(f"Today TS: {today_ts}")

active_df = df[df['expiry_dt'] >= today_ts]
print(f"\nActive DF Length: {len(active_df)}")

if active_df.empty:
    print("❌ BUG REPRODUCED: Active DF is empty because expiry parsing failed.")
    
    # PROPOSED FIX
    print("\n--- APPLYING FIX ---")
    # Fix: fillna with calculated date
    # note: we need to convert 'date' to datetime64 for arithmetic if it isn't already, or use apply
    
    def calc_expiry(row):
        if pd.isnull(row['expiry_dt']):
             return pd.Timestamp(row['date']) + timedelta(days=row['dte'])
        return row['expiry_dt']
        
    df['expiry_dt'] = df.apply(calc_expiry, axis=1)
    print("Fixed Expiry DT:")
    print(df['expiry_dt'])
    
    active_df_fixed = df[df['expiry_dt'] >= today_ts]
    print(f"Fixed Active DF Length: {len(active_df_fixed)}")
    
    if not active_df_fixed.empty:
        print("✅ FIX VERIFIED")
else:
    print("⚠️ BUG NOT REPRODUCED")
