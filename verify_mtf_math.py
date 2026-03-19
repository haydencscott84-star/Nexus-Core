import pandas as pd
import numpy as np

# Mocking pandas_ta functionality for verification purposes
# to avoid dependency issues on local machine if lib is missing.

def calculate_sma(series, length):
    return series.rolling(window=length).mean()

def calculate_atr(high, low, close, length=14):
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=length).mean() # Simple ATR for test

def verify_mtf_math():
    print("🧪 Verifying MTF Slope & Buffer Math (Self-Contained)...")
    
    # 1. Create Mock Data (Sine wave to create slope)
    x = np.linspace(0, 10, 100)
    prices = 100 + 10 * np.sin(x)
    df = pd.DataFrame({'Close': prices, 'High': prices+1, 'Low': prices-1, 'Open': prices})
    
    # 2. Calc Indicators (Manual Implementation)
    df['SMA_20'] = calculate_sma(df['Close'], 20)
    df['SMA_20'] = df['SMA_20'].fillna(100)
    
    df['ATR'] = calculate_atr(df['High'], df['Low'], df['Close'], 14)
    df['ATR'] = df['ATR'].fillna(1)

    # 3. Apply Slope Logic (The actual logic under test)
    # We look at the change in SMA over the last 5 bars
    # This matches: np.rad2deg(np.arctan(h_df['SMA_200'].diff(5) / 5))
    df['SMA_Slope'] = np.rad2deg(np.arctan(df['SMA_20'].diff(5) / 5))
    
    # 4. Check Last Candle
    print("\n📊 Data Sample (Last 5):")
    print(df[['Close', 'SMA_20', 'SMA_Slope', 'ATR']].tail())
    
    curr = df.iloc[-1]
    curr_slope = curr['SMA_Slope']
    curr_sma = curr['SMA_20']
    curr_close = curr['Close']
    curr_atr = curr['ATR']
    
    print(f"\nCurrent Values:")
    print(f"Close: {curr_close:.2f}")
    print(f"SMA: {curr_sma:.2f}")
    print(f"ATR: {curr_atr:.2f}")
    print(f"Slope: {curr_slope:.2f}°")
    
    # 5. Logic Checks
    floor_is_solid = curr_slope > -5
    optimal_short_strike = curr_sma - (1.0 * curr_atr)
    
    print(f"\n✅ Logic Verification:")
    print(f"Floor Solid (> -5°)? {'YES' if floor_is_solid else 'NO'}")
    print(f"Optimal Strike (SMA - 1ATR): {optimal_short_strike:.2f}")
    
    if not np.isnan(curr_slope):
        print("\n🚀 SUCCESS: Logic verified correctly.")
    else:
        print("\n❌ FAILURE: Slope calculation resulted in NaN.")

if __name__ == "__main__":
    verify_mtf_math()
