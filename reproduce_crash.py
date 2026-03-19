import pandas as pd
import numpy as np

def analyze_persistence(df):
    """
    Analyzes Position Persistence: OI Delta, Ghost, Fortress, VWAP.
    """
    if df.empty: return pd.DataFrame()
    
    # Group by Ticker, Strike, Expiry, Date
    # We want to aggregate metrics per day per contract
    daily_stats = df.groupby(['ticker', 'strike', 'expiry', 'date']).agg({
        'oi': 'max', # OI is usually a snapshot, max is safe for end of day
        'vol': 'sum',
        'premium': 'sum',
        'is_bull': lambda x: (x == True).sum() / len(x) if len(x) > 0 else 0 # Bull Ratio
    }).reset_index()
    
    daily_stats.sort_values(['ticker', 'strike', 'expiry', 'date'], inplace=True)
    
    # Calculate OI Delta
    daily_stats['prev_oi'] = daily_stats.groupby(['ticker', 'strike', 'expiry'])['oi'].shift(1)
    daily_stats['oi_delta'] = daily_stats['oi'] - daily_stats['prev_oi']
    daily_stats['oi_delta'] = daily_stats['oi_delta'].fillna(0)
    
    # VWAP Calculation (Cumulative for the period loaded)
    # Fix: VWAP = Total Premium / Total Volume (Weighted Average)
    daily_stats['avg_price'] = daily_stats['premium'] / daily_stats['vol'].replace(0, 1)
    
    # Ghost Filter: High Vol but Negative OI Delta
    # "Fresh Flow" usually means Vol > OI.
    # Ghost: Massive Fresh Flow on Day 1, but OI decreased on Day 2?
    # Simplified Ghost: High Vol today, but OI Delta is Negative or Zero.
    daily_stats['is_ghost'] = (daily_stats['vol'] > 1000) & (daily_stats['oi_delta'] <= 0)
    
    # Fortress Detector: OI Increased for 3 consecutive days
    # We need a rolling window check.
    daily_stats['oi_inc'] = daily_stats['oi_delta'] > 0
    
    print("DEBUG: daily_stats index before rolling assignment:", daily_stats.index)
    
    # THIS IS THE CRASH LINE
    try:
        # The original code:
        # daily_stats['fortress_count'] = daily_stats.groupby(['ticker', 'strike', 'expiry'])['oi_inc'].rolling(3).sum().reset_index(0, drop=True)
        
        # Let's see what the RHS looks like
        rolling_res = daily_stats.groupby(['ticker', 'strike', 'expiry'])['oi_inc'].rolling(3).sum()
        print("DEBUG: Rolling result index:", rolling_res.index)
        
        # Attempt assignment
        daily_stats['fortress_count'] = rolling_res.reset_index(level=[0,1,2], drop=True)
        print("DEBUG: Assignment successful (Modified approach)")
        
        # Reproduce the exact crash logic if possible, but I suspect the reset_index(0) was the issue
        # daily_stats['fortress_count'] = rolling_res.reset_index(0, drop=True) 
        
    except Exception as e:
        print(f"CRASH CAUGHT: {e}")

    daily_stats['is_fortress'] = daily_stats.get('fortress_count', 0) >= 3
    
    return daily_stats

# Create Dummy Data
data = {
    'ticker': ['SPY']*10,
    'strike': [500]*10,
    'expiry': ['2025-01-01']*10,
    'date': pd.date_range(start='2025-01-01', periods=10),
    'oi': [100, 110, 120, 130, 125, 135, 145, 155, 160, 170],
    'vol': [1000]*10,
    'premium': [5000]*10,
    'is_bull': [True]*10
}
df = pd.DataFrame(data)

print("Running reproduction...")
analyze_persistence(df)
print("Done.")
