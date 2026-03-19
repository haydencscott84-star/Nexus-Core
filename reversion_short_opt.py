import pandas as pd
import pandas_ta as ta
import vectorbt as vbt
import numpy as np
import itertools
from mtf_backtest import load_data, FEES, START_CAPITAL

# ==========================================
# 1. CONFIGURATION: Optimization Matrix
# ==========================================
RSI_THRESHOLDS = [70, 75, 80]
BB_STD_DEVS    = [2.0, 2.5, 3.0]
SMA_PERIOD     = 20       # The "Mean"
EXIT_SL_PCT    = 0.02     # 2% Safety Stop

def run_reversion_opt():
    print("🚀 Starting Mean Reversion Short Optimization (The Rubber Band)...")
    
    # 2. LOAD DATA
    h_df, _ = load_data() # We only need Hourly for this strategy
    
    # Ensure timezone naiveness
    if h_df.index.tz is not None: h_df.index = h_df.index.tz_localize(None)

    price = h_df['Close']
    print(f"Testing {len(RSI_THRESHOLDS) * len(BB_STD_DEVS)} Strategies on {len(h_df)} bars...")

    # 3. OPTIMIZATION LOOP
    entries_dict = {}
    exits_dict = {}
    
    combinations = list(itertools.product(RSI_THRESHOLDS, BB_STD_DEVS))
    
    for rsi_thresh, bb_std in combinations:
        label = f"RSI{rsi_thresh}_BB{bb_std}"
        
        # A. Calculate Indicators
        rsi = h_df.ta.rsi(length=14)
        
        bb = h_df.ta.bbands(length=20, std=bb_std)
        # Debug Columns
        # print(f"BB Columns for std {bb_std}: {bb.columns.tolist()}")

        # Safely extract by position to avoid naming variance
        # 0: Lower, 1: Middle (SMA), 2: Upper, 3: Bandwidth, 4: Percent
        upper_band = bb.iloc[:, 2]
        sma_20 = bb.iloc[:, 1]
        
        # B. Define Logic
        # SHORT ENTRY: Price > Upper Band AND RSI > Threshold
        entry_signal = (price > upper_band) & (rsi > rsi_thresh)
        
        # SHORT EXIT: Price < SMA 20 (Reverted to Mean)
        exit_signal = (price < sma_20)
        
        entries_dict[label] = entry_signal
        exits_dict[label] = exit_signal
        
    entries_df = pd.DataFrame(entries_dict)
    exits_df = pd.DataFrame(exits_dict)
    
    # 4. VECTORBT BACKTEST (With Stop Loss)
    # direction='shortonly' is critical
    # sl_stop=0.02 adds the 2% safety valve
    
    portfolio = vbt.Portfolio.from_signals(
        close=price,
        entries=entries_df,
        exits=exits_df,
        direction='shortonly', 
        sl_stop=EXIT_SL_PCT,
        init_cash=START_CAPITAL,
        fees=FEES,
        freq='1h'
    )
    
    # 5. RESULTS
    returns = portfolio.total_return() * 100
    
    print("\n🏆 --- TOP 5 REVERSION SETTINGS (Return %) ---")
    print(returns.sort_values(ascending=False).head(5))
    
    best_strategy = returns.idxmax()
    best_pf = portfolio[best_strategy]
    
    print(f"\n🥇 Winner: {best_strategy}")
    print(best_pf.stats())
    print(f"Safety Stop: {EXIT_SL_PCT*100}%")

if __name__ == "__main__":
    run_reversion_opt()
