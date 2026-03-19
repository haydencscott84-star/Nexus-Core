
import pandas as pd
import numpy as np
import datetime

def build_quant_payload(df):
    """
    Transforms raw option traps DataFrame into a structured Quant/Risk JSON object by Ticker.
    
    Args:
        df (pd.DataFrame): DataFrame with cols ['ticker', 'strike', 'expiry', 'status', 'net_delta', 'gamma', 'theta', 'spot_price'].
        
    Returns:
        dict: Structured risk analysis payload nested by ticker.
    """
    
    # 1. Validation
    if df.empty:
        return {"error": "Empty DataFrame"}
        
    # 2. Meta
    timestamp = datetime.datetime.now().isoformat()
    
    analysis = {}
    
    # 3. Group by Ticker (Distinct Ecosystems)
    tickers = df['ticker'].unique()
    
    for ticker in tickers:
        ticker_df = df[df['ticker'] == ticker]
        
        # Aggregations per Sub-Group
        bulls = ticker_df[ticker_df['status'] == 'TRAPPED BULLS']
        bears = ticker_df[ticker_df['status'] == 'TRAPPED BEARS']
        
        # Calculate Sums
        bull_gamma = bulls['gamma'].sum()
        bear_gamma = bears['gamma'].sum()
        
        # Instability Ratio (Bear / Bull) - Gamma Imbalance
        if abs(bull_gamma) < 1e-9:
             instability_ratio = 999.0 if abs(bear_gamma) > 1e-9 else 1.0
        else:
             instability_ratio = bear_gamma / bull_gamma
             
        # Regime Logic (Specific to Ticker)
        if ticker == 'SPX':
            regime = "WHALE STABILITY"
        elif ticker == 'SPY':
            regime = "RETAIL INSTABILITY"
        else:
            regime = "MARKET NEUTRAL"
            
        # Construct Ticker Analysis Node
        analysis[ticker] = {
            "regime": regime,
            "risk_vector": {
                "bull_gamma": round(float(bull_gamma), 4),
                "bear_gamma": round(float(bear_gamma), 4),
                "instability_ratio": round(float(instability_ratio), 4)
            }
        }
        
    return {
        "meta": {"timestamp": timestamp},
        "analysis": analysis,
        "spx_traps": df[df['ticker'] == 'SPX'].replace({np.nan: None}).to_dict(orient="records"),
        "spy_traps": df[df['ticker'] == 'SPY'].replace({np.nan: None}).to_dict(orient="records")
    }
