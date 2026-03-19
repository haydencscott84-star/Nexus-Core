
import pandas as pd
import glob
import os

files = sorted(glob.glob('/root/snapshots_spy/*.csv'))
if files:
    latest = files[-1]
    df = pd.read_csv(latest)
    print(f"File: {latest}")
    if 'stk' in df.columns: strike_col = 'stk'
    elif 'strike' in df.columns: strike_col = 'strike'
    else: print("No strike col"); exit()
    
    if 'vol' in df.columns: vol_col = 'vol'
    else: print("No vol col"); exit()
    
    # Filter for DTE <= 14 if dte exists
    if 'dte' in df.columns:
        df = df[pd.to_numeric(df['dte'], errors='coerce') <= 14]
        
    df['strike'] = pd.to_numeric(df[strike_col], errors='coerce')
    df['vol'] = pd.to_numeric(df[vol_col], errors='coerce')
    
    poc = df.groupby('strike')['vol'].sum().sort_values(ascending=False).head(10)
    print("Top 10 Volume by Strike (SPY, DTE <= 14):")
    print(poc)
