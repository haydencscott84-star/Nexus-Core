import pandas as pd
import pandas_ta as ta
import vectorbt as vbt
import numpy as itertools
import itertools
from mtf_backtest import load_data, FEES, START_CAPITAL

# ==========================================
# 1. CONFIGURATION: The "Short" Search Space
# ==========================================
HOURLY_SMA_PARAMS = [20, 50, 100, 200] 
DAILY_SMA_PARAMS  = [5, 8, 10, 21, 50]

def run_short_demo():
    print("🚀 Starting MTF Short Side Optimization...")
    
    # 2. LOAD DATA (Real Data from mtf_backtest logic)
    h_df, d_df = load_data()
    
    # Ensure timezone naiveness
    if h_df.index.tz is not None: h_df.index = h_df.index.tz_localize(None)
    if d_df.index.tz is not None: d_df.index = d_df.index.tz_localize(None)

    price_hourly = h_df['Close']
    
    print(f"Testing {len(HOURLY_SMA_PARAMS) * len(DAILY_SMA_PARAMS)} Short Strategies on {len(h_df)} bars...")

    # 3. OPTIMIZATION LOOP
    entries_dict = {}
    exits_dict = {}
    
    combinations = list(itertools.product(HOURLY_SMA_PARAMS, DAILY_SMA_PARAMS))
    
    for h_period, d_period in combinations:
        label = f"SHORT_H{h_period}_D{d_period}"
        
        # A. Calculate Indicators
        sma_hourly = h_df.ta.sma(length=h_period)
        
        # Daily Logic (Shifted & Aligned to avoid lookahead)
        d_sma = d_df.ta.sma(length=d_period)
        sma_daily_aligned = d_sma.shift(1).reindex(h_df.index).ffill()
        
        # B. Define Bearish Logic (THE FLIP)
        # Entry: Price BELOW Hourly SMA  AND  Price BELOW Daily SMA
        entry_signal = (price_hourly < sma_hourly) & (price_hourly < sma_daily_aligned)
        
        # Exit: Price RECOVERS ABOVE Hourly SMA (Stop Loss / Take Profit)
        exit_signal = (price_hourly > sma_hourly)
        
        entries_dict[label] = entry_signal
        exits_dict[label] = exit_signal
        
    entries_df = pd.DataFrame(entries_dict)
    exits_df = pd.DataFrame(exits_dict)
    
    # 4. RUN THE SHORT BACKTEST
    # NOTICE: direction='short' tells VectorBT we make money when price drops
    portfolio = vbt.Portfolio.from_signals(
        close=price_hourly,
        entries=entries_df,
        exits=exits_df,
        direction='shortonly',  # Critical: This calculates Short PnL
        init_cash=START_CAPITAL,
        fees=FEES,
        freq='1h'
    )
    
    # 5. RESULTS
    returns = portfolio.total_return() * 100
    
    print("\n🏆 --- TOP 5 BEARISH SETTINGS (Return %) ---")
    print(returns.sort_values(ascending=False).head(5))
    
    best_strategy = returns.idxmax()
    best_pf = portfolio[best_strategy]
    
    print(f"\n🥇 Winner: {best_strategy}")
    print(best_pf.stats())
    print(f"Computes based on {len(h_df)} hourly bars.")
if __name__ == "__main__":
    run_short_demo()
