import pandas as pd

try:
    df = pd.read_csv("spx_debug.csv")
    print(f"LOADED: {len(df)} rows")
    
    # Check for strikes < 1500
    if 'stk' in df.columns:
        df['strike'] = pd.to_numeric(df['stk'], errors='coerce')
        
        low_strikes = df[df['strike'] < 1500]
        if not low_strikes.empty:
            print(f"FOUND {len(low_strikes)} LOW STRIKES (< 1500):")
            print(low_strikes[['stk', 'type', 'vol', 'gamma']].head(10))
            
            # Check specifically for 1000
            strike_1000 = df[df['strike'] == 1000]
            if not strike_1000.empty:
                print("\nSTRIKE 1000 FOUND:")
                print(strike_1000[['stk', 'type', 'vol', 'gamma']])
        else:
            print("NO LOW STRIKES FOUND.")
            
except Exception as e:
    print(f"ERROR: {e}")
