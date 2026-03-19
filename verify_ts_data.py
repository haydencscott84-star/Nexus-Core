import sys
import os
import pandas as pd
import datetime

# Ensure local path is in sys.path
sys.path.append(os.getcwd())

try:
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
    from tradestation_explorer import TradeStationManager
except ImportError as e:
    print(f"Import Error: {e}")
    sys.exit(1)

print("--- VERIFYING TRADESTATION DATA ---\n")
try:
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
    
    print("Fetching Daily Bars (500)...")
    d_bars = ts.get_historical_data("SPY", unit="Daily", interval="1", bars_back="5")
    if d_bars:
        df = pd.DataFrame(d_bars)
        print("DAILY DATA (Last 5):")
        print(df[['TimeStamp', 'Close', 'High', 'Low']].tail())
    else:
        print("DAILY: No Data Returned")

    print("\nFetching Hourly Bars (100)...")
    h_bars = ts.get_historical_data("SPY", unit="Minute", interval="60", bars_back="5")
    if h_bars:
        df_h = pd.DataFrame(h_bars)
        print("HOURLY DATA (Last 5):")
        print(df_h[['TimeStamp', 'Close', 'High', 'Low']].tail())
    else:
        print("HOURLY: No Data Returned")

except Exception as e:
    print(f"FAILURE: {e}")
