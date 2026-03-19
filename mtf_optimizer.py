import pandas as pd
import pandas_ta as ta
import vectorbt as vbt
import numpy as itertools
import itertools
from mtf_backtest import load_data, FEES, START_CAPITAL

# ==========================================
# 1. CONFIGURATION: Define the "Search Space"
# ==========================================
HOURLY_SMA_PARAMS = [50, 100, 150, 200]
DAILY_SMA_PARAMS  = [8, 21, 50]

def run_optimization():
    print("🚀 Starting MTF Strategy Optimization...")
    
    # 2. LOAD DATA (Real Data from mtf_backtest logic)
    h_df, d_df = load_data()
    
    # Ensure timezone naiveness
    if h_df.index.tz is not None: h_df.index = h_df.index.tz_localize(None)
    if d_df.index.tz is not None: d_df.index = d_df.index.tz_localize(None)

    price_hourly = h_df['Close']
    
    print(f"Testing {len(HOURLY_SMA_PARAMS) * len(DAILY_SMA_PARAMS)} Strategy Combinations on {len(h_df)} bars...")

    # 3. OPTIMIZATION LOOP
    entries_dict = {}
    exits_dict = {}
    
    combinations = list(itertools.product(HOURLY_SMA_PARAMS, DAILY_SMA_PARAMS))
    
    for h_period, d_period in combinations:
        label = f"H{h_period}_D{d_period}"
        
        # A. Calculate Indicators
        # Normalize: Don't append to original DF to avoid column explosion, return Series
        sma_hourly = h_df.ta.sma(length=h_period)
        
        # Daily Logic (Aligned)
        # Shift Daily by 1 -> Reindex -> FFill
        d_sma = d_df.ta.sma(length=d_period)
        sma_daily_aligned = d_sma.shift(1).reindex(h_df.index).ffill()
        
        # B. Define Logic
        # Entry: Price > Hourly SMA AND Price > Daily SMA
        # (Note: Validating against User's logic request)
        entry_signal = (price_hourly > sma_hourly) & (price_hourly > sma_daily_aligned)
        
        # Exit: Price < Hourly SMA
        exit_signal = (price_hourly < sma_hourly)
        
        entries_dict[label] = entry_signal
        exits_dict[label] = exit_signal
        
    entries_df = pd.DataFrame(entries_dict)
    exits_df = pd.DataFrame(exits_dict)
    
    # 4. RUN VECTORIZED BACKTEST
    portfolio = vbt.Portfolio.from_signals(
        close=price_hourly,
        entries=entries_df,
        exits=exits_df,
        init_cash=START_CAPITAL,
        fees=FEES,
        freq='1h'
    )
    
    # 5. ANALYZE WINNERS
    returns = portfolio.total_return() * 100
    
    print("\n🏆 --- OPTIMIZATION RESULTS (Top 5 Return %) ---")
    print(returns.sort_values(ascending=False).head(5))
    
    best_strategy = returns.idxmax()
    print(f"\n🥇 Winner: {best_strategy}")
    print(portfolio[best_strategy].stats())
    
if __name__ == "__main__":
    run_optimization()
