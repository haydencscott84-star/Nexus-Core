
import pandas as pd
import numpy as np
import os
import sys

# Ensure local imports work by adding script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)


try:
    from orats_connector import get_live_chain
except ImportError:
    # If running in a place where import fails, mock it or fail gracefully
    # But for production deployment, it should work if orats_connector is present.
    print(f"Warning: orats_connector not found in {script_dir}")
    def get_live_chain(ticker): return pd.DataFrame()

from datetime import datetime
def log_timing(msg):
    print(f"[GREEKS_TIMING] {datetime.now().strftime('%H:%M:%S.%f')[:-3]} - {msg}")


def enrich_traps_with_greeks(traps_df):
    """
    Enriches the 'traps_df' with real-time Greeks from ORATS.
    
    Args:
        traps_df (pd.DataFrame): DataFrame with ['ticker', 'strike', 'expiry', 'option_type']
                                 'ticker' should be like 'SPY'
                                 'expiry' should be 'YYYY-MM-DD'
                                 'option_type' should be 'CALL' or 'PUT'
                                 'option_type' column might be named 'type' in some contexts, we handle both.
    
    Returns:
        pd.DataFrame: The enriched dataframe with delta, gamma, theta, vega, and greeks_exposure added.
    """
    print(f"[THREAD_DEBUG] 🚀 Start Enrichment for {len(traps_df)} rows.")
    
    if traps_df.empty:
        print("[THREAD_DEBUG] ⚠️ Empty DF, returning.")
        return traps_df

    # 1. Normalize Input Column Names
    # We need 'ticker', 'strike', 'expiry', 'type' (or 'option_type')
    df = traps_df.copy()
    if 'option_type' in df.columns and 'type' not in df.columns:
        df.rename(columns={'option_type': 'type'}, inplace=True)
        
    # 1.1 Validation
    required_cols = ['ticker', 'strike', 'expiry', 'type']
    if not all(col in df.columns for col in required_cols):
        print(f"[THREAD_DEBUG] ❌ Missing columns. Found: {df.columns.tolist()}. Required: {required_cols}")
        return traps_df # Return original if validation fails

    # 1.2 Add Greeks columns if missing (to ensure they exist for later filling)
    for col in ['delta', 'gamma', 'vega', 'theta']:
        if col not in df.columns:
            df[col] = 0.0

    # [OPTIMIZATION RESTORED] Skip fetch if Greeks are already present
    greeks_cols = ['delta', 'gamma', 'vega', 'theta']
    if all(col in df.columns for col in greeks_cols):
        # Check if they are actually populated (non-zero mean)
        # Some rows might be 0, but if the whole column is 0, we fetch.
        non_zero_count = df[greeks_cols].abs().sum().sum()
        if non_zero_count > 0:
            print("DEBUG: Greeks already present in input. Skipping live fetch.")
            return df
    
    # 2. Fetch Live Chain (Batch)
    # We assume all tickers in the df are the same (e.g. SPY/SPX). If mixed, we need to loop unique tickers.
    if 'ticker' not in df.columns:
        # Fallback if ticker is missing (unlikely for traps_df)
        return df

    import time # Ensure time is imported
    
    unique_tickers = df['ticker'].unique()
    
    live_dfs = []
    for ticker in unique_tickers:
        search_ticker = ticker
        if ticker == "SPX":
            search_ticker = "SPX" # Direct use of SPX (SPXW 404s)
            
        print(f"[THREAD_DEBUG] Fetching live chain for {search_ticker}...")
        try:
            chain = get_live_chain(search_ticker)
            if chain.empty and ticker == "SPX":
                 # Try fallback if SPX failed (e.g. maybe SPXW works sometimes?)
                 # But tracer showed SPX works.
                 pass 
            
            if not chain.empty:
                chain['ticker'] = ticker # Normalize back to input ticker (SPX) for merging
                live_dfs.append(chain)
            
            # [STAGGER] Prevent Rate Limiting
            print(f"[THREAD_DEBUG] Staggering... Sleeping 1.5s")
            time.sleep(1.5)
            
        except Exception as e:
            print(f"Error fetching Greeks for {ticker}: {e}")
            
    if not live_dfs:
        print(f"DEBUG: No live data fetched for tickers: {unique_tickers}")
        return df # Return original without greeks if fail
        
    master_chain = pd.concat(live_dfs, ignore_index=True)
    print(f"DEBUG: Fetched {len(master_chain)} rows from ORATS.")
    
    # DEBUG: Log Data State
    print(f"DEBUG: Master Chain Types: {master_chain.dtypes}")
    print(f"DEBUG: Input DF Types: {df.dtypes}")
    if not master_chain.empty:
        print(f"DEBUG: Live Expiry Sample: {master_chain['expiry'].head().tolist()}")
        print(f"DEBUG: Live Strike Sample: {master_chain['strike'].head().tolist()}")
    if not df.empty:
        print(f"DEBUG: Input Expiry Sample: {df['expiry'].head().tolist()}")
        print(f"DEBUG: Input Strike Sample: {df['strike'].head().tolist()}")
        
    # 3. Prepare for Merge WITH ROBUST NORMALIZATION
    # We need keys: ticker, strike, expiry, type
    
    # Normalize Strikes (Round to 1 decimal to avoid float precision issues)
    df['strike'] = pd.to_numeric(df['strike'], errors='coerce').round(1)
    master_chain['strike'] = pd.to_numeric(master_chain['strike'], errors='coerce')
    
    # 4. Merge Logic
    print("[THREAD_DEBUG] 🔄 Starting Merge...")
    # Normalize expiry formats
    try:
        df['expiry_dt'] = pd.to_datetime(df['expiry']).dt.strftime('%Y-%m-%d')
        master_chain['expiry_dt'] = pd.to_datetime(master_chain['expiry']).dt.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"[THREAD_DEBUG] ❌ Expiry Parse Error: {e}")
        return traps_df # Using traps_df here is incorrect, should be df
        
    # Ensure types are upper case
    df['type'] = df['type'].astype(str).str.upper()
    master_chain['type'] = master_chain['type'].astype(str).str.upper()

    # Merge
    # We want to keep all rows in df (Left Join)
    merged = pd.merge(
        df, 
        master_chain[['ticker', 'strike', 'expiry_dt', 'type', 'delta', 'gamma', 'theta', 'vega']],
        left_on=['ticker', 'strike', 'expiry_dt', 'type'],
        right_on=['ticker', 'strike', 'expiry_dt', 'type'],
        how='left',
        suffixes=('', '_live')
    )
    
    print(f"[THREAD_DEBUG] 🧩 Merge Done. Result rows: {len(merged)}")
    
    print(f"DEBUG: Merge Result - {len(merged)} rows. Columns: {list(merged.columns)}")
    # Check if we actually got any matches
    if 'delta_live' in merged.columns:
        matched = merged['delta_live'].notna().sum()
        print(f"DEBUG: Matched {matched} rows with live data.")
    else:
        print("DEBUG: 'delta_live' column missing after merge - likely no matches.")
    
    # 4. Fill NaNs (if no match found)
    for col in ['delta', 'gamma', 'theta', 'vega']:
        if f"{col}_live" in merged.columns:
            # If the original df already had delta, we might prefer the live one?
            # Start by taking the live one as primary
            merged[col] = merged[f"{col}_live"].fillna(merged.get(col, 0))
            merged.drop(columns=[f"{col}_live"], inplace=True)
        else:
            # If it wasn't there before, fill 0
            merged[col] = merged[col].fillna(0)

    # 5. Greeks Exposure Calculation
    # Gamma Exposure = Gamma * Size * 100
    size_col = 'vol' if 'vol' in merged.columns else ('size' if 'size' in merged.columns else None)
    
    if size_col:
        merged['greeks_exposure'] = merged['gamma'] * merged[size_col] * 100
    else:
        merged['greeks_exposure'] = 0.0
        
    return merged
