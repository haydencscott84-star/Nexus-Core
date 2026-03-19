import json
import os
import time
import datetime
import pandas as pd
import numpy as np
import pytz
from tradestation_connector import TradeStationConnector

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "nexus_structure.json")
TICKERS = ["SPY", "$SPX.X"]

# Initialize TS Connector
ts = TradeStationConnector()

def antigravity_dump(filename, data_dictionary):
    """
    Atomically dumps data and prints a heartbeat log.
    """
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
        
        # NEW: Print a timestamp so the user sees it is alive
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"✅ [HEARTBEAT] Wrote {filename} at {current_time}")
        
    except Exception as e:
        print(f"❌ DUMP ERROR: {e}")

def fetch_data(ticker):
    """
    Fetches market data using TradeStationConnector.
    """
    print(f"📉 Fetching data for {ticker} from TradeStation...")
    
    # 1. Daily Data for SMAs (1 Year ~ 252 bars)
    daily_candles = ts.fetch_candles(ticker, interval="Daily", unit="Daily", bars=252)
    daily_df = pd.DataFrame(daily_candles)
    
    # 2. Intraday Data for VWAP (1 Day ~ 390 minutes)
    intraday_candles = ts.fetch_candles(ticker, interval=1, unit="Minute", bars=390)
    intraday_df = pd.DataFrame(intraday_candles)
    
    # 3. Hourly Data for Hourly SMAs (200 hours ~ 2-3 weeks)
    hourly_candles = ts.fetch_candles(ticker, interval=60, unit="Minute", bars=300)
    hourly_df = pd.DataFrame(hourly_candles)
    
    return daily_df, intraday_df, hourly_df

def calculate_sma(df, window):
    if df.empty or len(df) < window: return 0.0
    return float(df['Close'].rolling(window=window).mean().iloc[-1])

def calculate_vwap(df):
    """
    Calculates Volume Weighted Average Price for the session.
    """
    if df.empty: return 0.0
    
    # VWAP = Cumulative(Price * Volume) / Cumulative(Volume)
    # Using Close price as proxy for Typical Price if High/Low/Close not fully reliable or for simplicity
    # Standard VWAP uses Typical Price: (H+L+C)/3
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    vwap = (tp * df['Volume']).cumsum() / df['Volume'].cumsum()
    return float(vwap.iloc[-1])

def calculate_hourly_rvol(hourly_df):
    """
    Calculates RVOL for the current hour compared to the average volume 
    of that specific hour over the available history.
    """
    try:
        if hourly_df.empty: return 0.0, 0.0

        # Ensure datetime index
        if 'Date' in hourly_df.columns:
            hourly_df['Date'] = pd.to_datetime(hourly_df['Date'])
            
        # Get the latest bar
        last_bar = hourly_df.iloc[-1]
        last_date = last_bar['Date']
        current_vol = float(last_bar['Volume'])
        
        # Determine target hour (using the hour of the last bar)
        # Note: TS candles are usually referenced by open or close time. 
        # We just match the hour component.
        target_hour = last_date.hour
        
        # Filter for bars with the same hour, EXCLUDING the current incomplete bar if we were strictly doing history
        # But for RVOL we want to compare current (potentially developing) to historical average.
        # Let's exclude the exact same date to get "historical average"
        historical_bars = hourly_df[
            (hourly_df['Date'].dt.hour == target_hour) & 
            (hourly_df['Date'].dt.date != last_date.date())
        ]
        
        if historical_bars.empty:
            avg_vol = current_vol # Fallback if no history
        else:
            avg_vol = historical_bars['Volume'].mean()
            
        rvol = current_vol / avg_vol if avg_vol > 0 else 0.0
        
        return float(rvol), float(avg_vol)

    except Exception as e:
        print(f"⚠️ Hourly RVOL Error: {e}")
        return 0.0, 0.0

def calculate_force_index(df, ema_span=13):
    """
    Calculates 13-Period Force Index with Vol Outlier Clipping.
    FI = (Close - Prev_Close) * Volume
    Scaled by 100M for readability.
    Returns: force_index (float), trend_strength (0-100)
    """
    try:
        if df.empty or len(df) < 50: return 0.0, 50.0

        w_df = df.copy()
        
        # 1. Outlier Clipping (3x StdDev Cap on Volume)
        vol_mean = w_df['Volume'].rolling(window=20).mean()
        vol_std = w_df['Volume'].rolling(window=20).std()
        
        # Calculate Cap (Scalar or Series)
        # Using a specialized apply or direct numpy clip is faster
        # Here we do a vector calculation for robustness
        upper_limit = vol_mean + (3 * vol_std)
        
        # Apply Cap: Where Volume > Limit, use Limit
        w_df['Capped_Volume'] = np.where(w_df['Volume'] > upper_limit, upper_limit, w_df['Volume'])
        
        # 2. Raw Force
        # Force = Change * Volume
        w_df['Change'] = w_df['Close'].diff()
        w_df['Raw_Force'] = w_df['Change'] * w_df['Capped_Volume']
        
        # 3. Smoothing (13 EMA)
        w_df['Force_13'] = w_df['Raw_Force'].ewm(span=ema_span, adjust=False).mean()
        
        # 4. Scaling (100M)
        current_fi = float(w_df['Force_13'].iloc[-1]) / 100_000_000
        
        # 5. Trend Strength (Normalized 0-100 over 21 days)
        # We look at the MAGNITUDE (Abs) of the Force to determine Strength
        # Or should strength be directional? 
        # Requirement: "Trend Strength" implies conviction.
        # Let's use Normalized RSI-style or Min/Max.
        # User asked for "Normalized 0-100 score derived from Force Index magnitude relative to last 21 days".
        
        subset = w_df['Force_13'].iloc[-22:]
        min_fi = subset.min()
        max_fi = subset.max()
        
        # Current Value in Range
        last_raw_fi = float(w_df['Force_13'].iloc[-1])
        
        if max_fi != min_fi:
            strength = ((last_raw_fi - min_fi) / (max_fi - min_fi)) * 100
        else:
            strength = 50.0
            
        return current_fi, min(max(strength, 0.0), 100.0)

    except Exception as e:
        print(f"⚠️ Force Index Error: {e}")
        return 0.0, 50.0

def run_structure_cycle():
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] starting Cycle...")
    
    structure_snapshot = {"timestamp": time.time()}

    for ticker in TICKERS:
        try:
            print(f"   Analysing {ticker}...")
            daily_df, intraday_df, hourly_df = fetch_data(ticker)
            
            if daily_df.empty:
                print(f"❌ {ticker}: Data Fetch Failed or Empty.")
                continue

            # --- TECHNICAL ANALYSIS ENGINE ---
            # 1. Ensure Data is Sorted
            daily_df = daily_df.sort_values(by="Date", ascending=True)

            # 2. Calculate The "Big Three"
            col_sma20 = daily_df['Close'].rolling(window=20).mean()
            col_sma50 = daily_df['Close'].rolling(window=50).mean()
            col_sma200 = daily_df['Close'].rolling(window=200).mean()
            col_vol_sma20 = daily_df['Volume'].rolling(window=20).mean()

            # 3. Extract Latest Values
            last_row = daily_df.iloc[-1]
            
            # STANDARD RVOL (Daily)
            avg_vol = float(col_vol_sma20.iloc[-1]) if pd.notnull(col_vol_sma20.iloc[-1]) else 1.0
            curr_vol = float(last_row['Volume'])
            rvol_val = curr_vol / avg_vol if avg_vol > 0 else 0.0

            # NEW: HOURLY RVOL
            hourly_rvol_val, hourly_avg_vol = calculate_hourly_rvol(hourly_df)

            # NEW: FORCE INDEX
            force_index, trend_strength = calculate_force_index(daily_df)
            force_index_2, _ = calculate_force_index(daily_df, ema_span=2) # NEW: 2-EMA

            # Use live price from intraday for accuracy if available
            if not intraday_df.empty:
                current_price = float(intraday_df['Close'].iloc[-1])
            else:
                current_price = float(last_row['Close'])
            
            sma_20 = float(col_sma20.iloc[-1]) if pd.notnull(col_sma20.iloc[-1]) else 0.0
            sma_50 = float(col_sma50.iloc[-1]) if pd.notnull(col_sma50.iloc[-1]) else 0.0
            sma_200 = float(col_sma200.iloc[-1]) if pd.notnull(col_sma200.iloc[-1]) else 0.0

            # Calculate Hourly SMAs
            hourly_sma_20 = 0.0
            hourly_sma_50 = 0.0
            hourly_sma_200 = 0.0
            
            if not hourly_df.empty:
                hourly_df = hourly_df.sort_values(by="Date", ascending=True)
                h_sma20 = hourly_df['Close'].rolling(window=20).mean()
                h_sma50 = hourly_df['Close'].rolling(window=50).mean()
                h_sma200 = hourly_df['Close'].rolling(window=200).mean()
                
                last_hr = hourly_df.iloc[-1]
                hourly_sma_20 = float(h_sma20.iloc[-1]) if pd.notnull(h_sma20.iloc[-1]) else 0.0
                hourly_sma_50 = float(h_sma50.iloc[-1]) if pd.notnull(h_sma50.iloc[-1]) else 0.0
                hourly_sma_200 = float(h_sma200.iloc[-1]) if pd.notnull(h_sma200.iloc[-1]) else 0.0

            # 4. Calculate Trend Logic
            # A. The Stack (Trend Health)
            if sma_20 > sma_50 > sma_200:
                stack_status = "BULLISH_STACK (Full Alignment)"
            elif sma_20 < sma_50 < sma_200:
                stack_status = "BEARISH_STACK (Full Alignment)"
            else:
                stack_status = "CHAOTIC_STACK (Indecision/Transition)"

            # B. The Extension (Rubber Band)
            if sma_20 > 0:
                extension_pct = ((current_price - sma_20) / sma_20) * 100
            else:
                extension_pct = 0.0
                
            extension_status = "NORMAL"
            if extension_pct > 3.0: extension_status = "OVEREXTENDED_UPSIDE (Risk of Pullback)"
            elif extension_pct < -3.0: extension_status = "OVEREXTENDED_DOWNSIDE (Risk of Bounce)"
            
            # Calculate 200 SMA Extension
            extension_200_pct = 0.0
            if sma_200 > 0:
                extension_200_pct = ((current_price - sma_200) / sma_200) * 100
            
            # Calculate VWAP
            vwap_val = calculate_vwap(intraday_df)

            # 5. Construct Structure Output
            key = "SPX" if ticker == "$SPX.X" else ticker
            structure_snapshot[key] = {
                "price": current_price,
                "levels": {
                    "vwap": round(vwap_val, 2),
                    "sma_20": round(sma_20, 2),
                    "sma_50": round(sma_50, 2),
                    "sma_200": round(sma_200, 2),
                    "hourly_sma_20": round(hourly_sma_20, 2),
                    "hourly_sma_50": round(hourly_sma_50, 2),
                    "hourly_sma_200": round(hourly_sma_200, 2)
                },
                "trend_metrics": {
                    "stack_status": stack_status,
                    "extension_from_20sma": round(extension_pct, 2),
                    "extension_from_200sma": round(extension_200_pct, 2),
                    "extension_status": extension_status,
                    "price_vs_vwap": "ABOVE" if current_price > vwap_val else "BELOW",
                    "price_vs_200ma": "ABOVE" if current_price > sma_200 else "BELOW",
                    "hourly_stack": "BULL" if hourly_sma_20 > hourly_sma_50 else "BEAR",
                    "rvol": round(rvol_val, 2),
                    "hourly_rvol": round(hourly_rvol_val, 2), # NEW
                    "hourly_avg_vol": round(hourly_avg_vol, 2), # NEW (Debug info)
                    "force_index_13": round(force_index, 3), # NEW
                    "force_index_2": round(force_index_2, 3), # NEW
                    "trend_strength": round(trend_strength, 1) # NEW
                }
            }
            
            print(f"   -> {ticker} VWAP: {vwap_val:.2f} | RVOL: {rvol_val:.1f} | FI: {force_index:+.2f} ({trend_strength:.0f})")

        except Exception as e:
            print(f"❌ {ticker} Calculation Error: {e}")

    # Atomic Dump
    antigravity_dump(OUTPUT_FILE, structure_snapshot)

def main():
    print("Starting Structure Nexus (Multi-Ticker Edition)...")
    while True:
        try:
            run_structure_cycle()
        except Exception as e:
            print(f"Structure Cycle Error: {e}")
        
        # Sleep 5 minutes
        print("Sleeping 5 minutes...")
        time.sleep(300)

if __name__ == "__main__":
    main()
