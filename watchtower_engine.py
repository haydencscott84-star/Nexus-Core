import yfinance as yf
import pandas as pd
import numpy as np
import json
import os
import datetime
import sys
import warnings

# Suppress yfinance FutureWarnings
warnings.simplefilter(action='ignore', category=FutureWarning)

OUTPUT_FILE = "market_state_live.json"

import requests

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")

def fetch_uw_history(ticker, uw_symbol):
    """Fetches daily closes from Unusual Whales as backup."""
    url = f"https://api.unusualwhales.com/api/stock/{uw_symbol}/ohlc/1d"
    headers = {"Authorization": f"Bearer {UW_API_KEY}", "Accept": "application/json"}
    params = {"limit": 130} # Approx 6 months
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if not data: return None
            
            df = pd.DataFrame(data)
            df['Date'] = pd.to_datetime(df['date'])
            df.drop_duplicates(subset=['Date'], keep='last', inplace=True) # Fix: Drop dupes
            df.set_index('Date', inplace=True)
            df.sort_index(inplace=True)
            return df['close'].astype(float)
    except: pass
    return None

def fetch_orats_history(ticker, orats_symbol):
    """Fetches 6 months of daily closes from ORATS."""
    url = "https://api.orats.io/datav2/hist/dailies"
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=180)
    
    params = {
        "token": ORATS_API_KEY,
        "ticker": orats_symbol,
        "tradeDate[gte]": start_date.strftime("%Y-%m-%d"),
        "tradeDate[lte]": end_date.strftime("%Y-%m-%d"),
        "fields": "tradeDate,clsPx"
    }
    
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if not data: return None
            
            # Convert to Series
            df = pd.DataFrame(data)
            df['Date'] = pd.to_datetime(df['tradeDate'])
            df.set_index('Date', inplace=True)
            df.sort_index(inplace=True)
            return df['clsPx'].astype(float)
        else:
            print(f"   ❌ ORATS Error {r.status_code} for {orats_symbol}")
    except Exception as e:
        print(f"   ❌ ORATS Exception for {orats_symbol}: {e}")
    return None

def fetch_data():
    print("   Fetching Data (Hybrid: ORATS -> UW -> yfinance)...")
    
    # 1. Fetch Core from ORATS (Primary Institutional)
    spy_series = fetch_orats_history("SPY", "SPY")
    rsp_series = fetch_orats_history("RSP", "RSP")
    vix_series = fetch_orats_history("^VIX", "VIX")
    
    # 2. Backup: Unusual Whales (Secondary Institutional)
    if spy_series is None:
        print("   ⚠️ ORATS SPY Failed. Trying Unusual Whales...")
        spy_series = fetch_uw_history("SPY", "SPY")
        
    if rsp_series is None:
        print("   ⚠️ ORATS RSP Failed. Trying Unusual Whales...")
        rsp_series = fetch_uw_history("RSP", "RSP")
        
    # Note: UW does not support VIX/VIX3M/VVIX history via API
    
    # 3. Fetch Exotics from yfinance (Retail Fallback)
    yf_tickers = ["^VIX3M", "^VVIX"]
    
    # Fallback logic if everything fails
    if spy_series is None:
        print("   ⚠️ All Institutional Feeds Failed. Falling back to full yfinance.")
        yf_tickers = ["SPY", "RSP", "^VIX", "^VIX3M", "^VVIX"]
    
    try:
        yf_data = yf.download(yf_tickers, period="6mo", progress=False)['Close']
    except:
        yf_data = pd.DataFrame()

    # 4. Merge
    df = pd.DataFrame()
    
    if spy_series is not None:
        df["SPY"] = spy_series
        # Use yfinance RSP/VIX if ORATS/UW failed individually but SPY succeeded
        if rsp_series is not None: df["RSP"] = rsp_series
        if vix_series is not None: df["^VIX"] = vix_series
    else:
        # Full fallback
        df = yf_data
        return df

    # Join yfinance columns
    if not yf_data.empty:
        # yfinance might return Series if single ticker, or DataFrame
        if isinstance(yf_data, pd.Series):
            df[yf_tickers[0]] = yf_data
        else:
            for col in yf_data.columns:
                # Avoid overwriting if we already have it from Inst source
                if col not in df.columns:
                    df[col] = yf_data[col]
    
    # Fill forward/back to align dates
    df.fillna(method='ffill', inplace=True)
    df.dropna(inplace=True) # Drop rows where we don't have overlapping data
    
    return df

def calculate_metrics(df):
    if df is None or df.empty: return None

    # Get latest row
    last = df.iloc[-1]
    
    # 1. Term Structure (Panic)
    vix = last.get("^VIX", 0)
    vix3m = last.get("^VIX3M", 0)
    term_structure_ratio = vix / vix3m if vix3m > 0 else 0
    term_structure_inverted = term_structure_ratio > 1.05

    # 2. Breadth Divergence (10-Day Slope)
    # Calculate Ratio Series
    ratio = df["RSP"] / df["SPY"]
    # Calculate 10-day returns of the ratio
    ratio_10d_change = ratio.pct_change(10).iloc[-1]
    spy_10d_change = df["SPY"].pct_change(10).iloc[-1]
    
    # Divergence: SPY Up (>1%) AND Ratio Down (<-1%)
    breadth_divergence = (spy_10d_change > 0.01) and (ratio_10d_change < -0.01)

    # 3. Velocity (Rolling Volatility)
    spy_returns = df["SPY"].pct_change()
    rolling_vol = spy_returns.rolling(window=5).std()
    current_vol = rolling_vol.iloc[-1]
    # Percentile Rank
    vol_rank = rolling_vol.rank(pct=True).iloc[-1]
    volatility_expansion = vol_rank > 0.80

    # 4. Regime State
    spy_price = last["SPY"]
    sma_50 = df["SPY"].rolling(window=50).mean().iloc[-1]
    
    regime = "UNKNOWN"
    if spy_price > sma_50:
        if vix < 20: regime = "BULL_QUIET"
        else: regime = "BULL_VOLATILE"
    else:
        if vix < 25: regime = "BEAR_QUIET"
        else: regime = "BEAR_VOLATILE"

    # 5. Alert Level
    alert_level = "GREEN"
    if regime == "BEAR_VOLATILE" or term_structure_inverted:
        alert_level = "RED"
    elif regime == "BULL_VOLATILE" or breadth_divergence or volatility_expansion:
        alert_level = "YELLOW"

    # Message
    msgs = []
    if term_structure_inverted: msgs.append("Term Structure Inverted (Panic).")
    if breadth_divergence: msgs.append("Breadth Divergence (Thin Rally).")
    if volatility_expansion: msgs.append("Volatility Expanding.")
    if not msgs: msgs.append("Market conditions are stable.")
    
    return {
        "timestamp": datetime.datetime.now().isoformat(),
        "regime": regime,
        "alert_level": alert_level,
        "consensus_votes": {
             "term_structure_inverted": bool(term_structure_inverted),
             "breadth_divergence": bool(breadth_divergence),
             "volatility_expansion": bool(volatility_expansion)
        },
        "metrics": {
            "vix": round(vix, 2),
            "vix_ratio": round(term_structure_ratio, 3),
            "spy_price": round(spy_price, 2),
            "sma_50": round(sma_50, 2)
        },
        "message": " ".join(msgs)
    }

def run_watchtower():
    print(f"🔭 Watchtower Scan at {datetime.datetime.now().strftime('%H:%M:%S')}...")
    df = fetch_data()
    state = calculate_metrics(df)
    
    if state:
        with open(OUTPUT_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"✅ State Updated: {state['regime']} | Alert: {state['alert_level']}")
        print(f"   Msg: {state['message']}")
    else:
        print("⚠️ Watchtower failed to update state.")

import time
import sys

if __name__ == "__main__":
    # Force Loop Mode by default for Service Stability
    print("🔄 Watchtower starting in LOOP mode (Default)...")
    while True:
        try:
            run_watchtower()
        except Exception as e:
            print(f"❌ Watchtower Crash: {e}")
        
        print("💤 Sleeping 60m...")
        time.sleep(3600)
