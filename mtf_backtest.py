import pandas as pd
import pandas_ta as ta
import numpy as np
import os
import sys
from datetime import datetime, timedelta

# --- IMPORTS & FALLBACKS ---
try:
    import vectorbt as vbt
    HAS_VBT = True
except ImportError:
    HAS_VBT = False
    print("⚠️  'vectorbt' not found. Using lightweight Pandas Backtester for Pilot.")

# Try to import TradeStation Manager
try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
    HAS_TS = True
except ImportError:
    HAS_TS = False
    print("⚠️  TradeStation modules not found. Will use Local CSV or Synthetic Data.")

# --- CONFIGURATION ---
HOURLY_FILE = "hourly.csv"
DAILY_FILE = "daily.csv"
TICKER = "SPY"
START_CAPITAL = 10000
FEES = 0.001 # 0.1%

def generate_mock_data(days=365):
    """Generates synthetic Hourly and Daily OHLCV data using a random walk."""
    print("⚠️  Files/API missing. Generating SYNTHETIC MOCK DATA for testing...")
    end_date = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)
    
    hourly_index = pd.date_range(start=start_date, end=end_date, freq='1h') # Changed freq to 1h for compatibility
    n_hourly = len(hourly_index)
    
    np.random.seed(42)
    returns = np.random.normal(loc=0.0001, scale=0.002, size=n_hourly)
    price_path = 100 * np.cumprod(1 + returns)
    
    hourly_df = pd.DataFrame({
        'Open': price_path, 'High': price_path * 1.001, 'Low': price_path * 0.999, 'Close': price_path,
        'Volume': np.random.randint(1000, 10000, size=n_hourly)
    }, index=hourly_index)
    
    daily_df = hourly_df.resample('D').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    return hourly_df, daily_df

def fetch_ts_data():
    """Fetches real data from TradeStation if available."""
    if not HAS_TS: return None, None
    print(f"🔄 Connecting to TradeStation for {TICKER} data...")
    try:
        ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
        
        # Hourly Data (Last 1 Year)
        # 1 Year * 252 Days * 7 Hours = ~1764 bars. Safe buffer 2000.
        print("   fetching hourly...")
        h_bars = ts.get_historical_data(TICKER, unit="Minute", interval="60", bars_back="2000")
        
        # Daily Data (Last 2 Years for indicators)
        print("   fetching daily...")
        d_bars = ts.get_historical_data(TICKER, unit="Daily", interval="1", bars_back="500")
        
        if not h_bars or not d_bars: 
            print("❌ TradeStation returned empty data.")
            return None, None
            
        def process(bars):
            df = pd.DataFrame(bars)
            date_col = 'TimeStamp' if 'TimeStamp' in df.columns else 'Timestamp'
            df['Close'] = pd.to_numeric(df['Close'])
            df['Open'] = pd.to_numeric(df['Open']) # Needed for backtest entry/exit realism? usually use Close for simple
            df.index = pd.to_datetime(df[date_col])
            return df.sort_index()

        return process(h_bars), process(d_bars)
        
    except Exception as e:
        print(f"❌ TradeStation Error: {e}")
        return None, None

def load_data():
    # 1. Local Files
    if os.path.exists(HOURLY_FILE) and os.path.exists(DAILY_FILE):
        print(f"✅ Loading local files: {HOURLY_FILE}, {DAILY_FILE}")
        return pd.read_csv(HOURLY_FILE, index_col=0, parse_dates=True), pd.read_csv(DAILY_FILE, index_col=0, parse_dates=True)
    
    # 2. TradeStation
    h, d = fetch_ts_data()
    if h is not None: 
        # Optional: Save for next time?
        # h.to_csv(HOURLY_FILE); d.to_csv(DAILY_FILE)
        return h, d
        
    # 3. Synthetic
    return generate_mock_data()

def simple_pandas_backtest(h_df, entries, exits):
    """
    A lightweight vectorized backtester using Pandas.
    Used when vectorbt is missing.
    Assumes: Buy on Next Open (or Close if simplified) after Signal.
    Simplified: Buy at Close of Signal Candle.
    """
    print("⚙️  Running Pandas-based Backtest Engine...")
    
    #Combine into a frame
    bt = pd.DataFrame(index=h_df.index)
    bt['Close'] = h_df['Close']
    bt['Signal'] = 0
    bt.loc[entries, 'Signal'] = 1 # Enter Long
    bt.loc[exits, 'Signal'] = -1  # Exit Long
    
    # State Machine for positions
    # 1 = Long, 0 = Cash
    position = 0
    trades = []
    equity = START_CAPITAL
    
    in_price = 0
    
    # Iterative approach is safer for correctness in a pilot than generic vectorization bugs
    for i in range(len(bt)):
        price = bt['Close'].iloc[i]
        sig = bt['Signal'].iloc[i]
        
        if position == 0 and sig == 1:
            # BUY
            position = 1
            in_price = price
            equity -= equity * FEES # Entry Fee
            
        elif position == 1 and sig == -1:
            # SELL
            position = 0
            pnl_pct = (price - in_price) / in_price
            equity = equity * (1 + pnl_pct)
            equity -= equity * FEES # Exit Fee
            trades.append(pnl_pct)
            
    # Final cleanup
    total_return = (equity - START_CAPITAL) / START_CAPITAL * 100
    win_rate = (sum(x > 0 for x in trades) / len(trades) * 100) if trades else 0
    
    print("\n📊 PANDAS BACKTEST RESULTS:")
    print("-------------------------")
    print(f"End Capital: ${equity:,.2f}")
    print(f"Total Return: {total_return:.2f}%")
    print(f"Total Trades: {len(trades)}")
    print(f"Win Rate:     {win_rate:.1f}%")

def run_backtest():
    h_df, d_df = load_data()
    
    # Indicators
    h_df.ta.sma(length=200, append=True) 
    d_df.ta.sma(length=8, append=True)
    d_df.ta.sma(length=21, append=True)
    
    # ALIGNMENT (Shift + Broadcast)
    # Ensure timezone naiveness or matching
    if h_df.index.tz is not None: h_df.index = h_df.index.tz_localize(None)
    if d_df.index.tz is not None: d_df.index = d_df.index.tz_localize(None)

    d_sma_8 = d_df['SMA_8'].shift(1).reindex(h_df.index).ffill()
    d_sma_21 = d_df['SMA_21'].shift(1).reindex(h_df.index).ffill()
    sma_200_h = h_df['SMA_200']
    
    # Debug Alignment
    print("\n🧐 Alignment Check (First 3 rows):")
    print(pd.DataFrame({'H_Close':h_df['Close'], 'D_SMA8':d_sma_8}).dropna().head(3))
    
    # Strategy
    # Entries: Hourly Close > 200 SMA AND Price > Daily 8 SMA AND Daily 8 > Daily 21
    entries = (h_df['Close'] > sma_200_h) & (h_df['Close'] > d_sma_8) & (d_sma_8 > d_sma_21)
    
    # Exits: Hourly Close < 200 SMA
    exits = h_df['Close'] < sma_200_h
    
    if HAS_VBT:
        portfolio = vbt.Portfolio.from_signals(
            close=h_df['Close'], entries=entries, exits=exits, 
            init_cash=START_CAPITAL, fees=FEES, freq='1h'
        )
        print("\n📊 VECTORBT RESULTS:")
        print(portfolio.stats())
    else:
        simple_pandas_backtest(h_df, entries, exits)

if __name__ == "__main__":
    run_backtest()
