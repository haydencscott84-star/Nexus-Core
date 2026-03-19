import pandas as pd
import numpy as np
import asyncio
import os
import sys
from datetime import datetime, timedelta

try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except ImportError:
    print("❌ Critical: Run this from your Nexus root folder.")
    sys.exit(1)

# --- CONFIGURATION ---
TICKER = "SPY"
YEARS_BACK = 10
SMA_PERIOD = 200

async def run_backtest():
    print(f"📉 STARTING MEAN REVERSION BACKTEST: {TICKER} ({YEARS_BACK} Years)")
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
    
    # 252 trading days * 10 years + buffer
    bars_needed = (252 * YEARS_BACK) + SMA_PERIOD + 50
    print(f"   -> Fetching {bars_needed} daily candles...")
    
    candles = ts.get_historical_data(TICKER, unit="Daily", interval="1", bars_back=str(bars_needed))
    if not candles:
        print("❌ Error: No data returned.")
        return

    df = pd.DataFrame(candles)
    df['Close'] = pd.to_numeric(df['Close'])
    df['Date'] = pd.to_datetime(df['TimeStamp']) # Adjust key if needed
    df = df.sort_values('Date')
    
    # Calculate Indicators
    df['SMA_200'] = df['Close'].rolling(window=SMA_PERIOD).mean()
    df['Extension_Pct'] = ((df['Close'] - df['SMA_200']) / df['SMA_200']) * 100
    
    # Forward Returns (Did it revert?)
    df['Ret_5d'] = df['Close'].shift(-5) - df['Close']
    df['Ret_10d'] = df['Close'].shift(-10) - df['Close']
    df['Ret_20d'] = df['Close'].shift(-20) - df['Close']
    df = df.dropna()

    print("\n📊 BACKTEST RESULTS: 200 SMA EXTENSION")
    print(f"{'EXTENSION':<15} | {'COUNT':<6} | {'5D REV%':<10} | {'20D REV%':<10}")
    print("-" * 55)
    
    bins = [0, 5, 10, 15, 20, 100]
    
    # UPSIDE EXTENSION
    print(">>> PRICE ABOVE 200 SMA (Short Setup)")
    for i in range(len(bins)-1):
        low = bins[i]; high = bins[i+1]
        subset = df[(df['Extension_Pct'] > low) & (df['Extension_Pct'] <= high)]
        if len(subset) == 0: continue
        
        # Reversion = Price went DOWN
        rev_5 = (subset['Ret_5d'] < 0).mean() * 100
        rev_20 = (subset['Ret_20d'] < 0).mean() * 100
        print(f"+{low}% to +{high}%   | {len(subset):<6} | {rev_5:>7.1f}% | {rev_20:>7.1f}%")

    print("-" * 55)
    # DOWNSIDE EXTENSION
    print(">>> PRICE BELOW 200 SMA (Long Setup)")
    for i in range(len(bins)-1):
        low = bins[i]; high = bins[i+1]
        subset = df[(df['Extension_Pct'] < -low) & (df['Extension_Pct'] >= -high)]
        if len(subset) == 0: continue
        
        # Reversion = Price went UP
        rev_5 = (subset['Ret_5d'] > 0).mean() * 100
        rev_20 = (subset['Ret_20d'] > 0).mean() * 100
        print(f"-{low}% to -{high}%   | {len(subset):<6} | {rev_5:>7.1f}% | {rev_20:>7.1f}%")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_backtest())
