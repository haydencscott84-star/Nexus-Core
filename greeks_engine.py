import pandas as pd
import numpy as np
from py_vollib_vectorized import vectorized_implied_volatility, get_all_greeks

# --- 1. THE ADAPTER (Tuned for 30DTE) ---
def adapter_swing_trade(api_response):
    """
    Parses a TradeStation/Orats response and ensures the Expiration Date 
    is set correctly to 4:00 PM ET on the future date.
    """
    # Parse the date string provided by the API (e.g., "12/20/2025")
    # We add " 16:00:00" to ensure we calculate T until market close
    raw_date = api_response.get('ExpirationDate') # e.g., "2025-12-20"
    expiry_timestamp = pd.to_datetime(raw_date) + pd.Timedelta(hours=16)

    mapped_data = {
        'strike': [float(api_response.get('StrikePrice'))], 
        'type': ['c' if 'Call' in str(api_response.get('OptionType')) else 'p'], 
        'option_price': [float(api_response.get('LastPrice'))], 
        'underlying_price': [float(api_response.get('UnderlyingPrice'))],
        'expiry_date': [expiry_timestamp] # This is now a future date
    }

    return pd.DataFrame(mapped_data)

# --- 2. THE ENGINE (Standard Black-Scholes) ---
def calculate_greeks_30dte(df, risk_free_rate=0.0425):
    """
    Calculates Greeks. 
    risk_free_rate defaults to 4.25% (approx 1-month Treasury yield)
    """
    # Calculate Time to Expiration (T) in Years
    now = pd.Timestamp.now()
    df['T'] = (df['expiry_date'] - now).dt.total_seconds() / (365 * 24 * 60 * 60)
    
    # Calculate IV first (The 'Price' of the option)
    df['iv'] = vectorized_implied_volatility(
        price=df['option_price'],
        S=df['underlying_price'],
        K=df['strike'],
        t=df['T'],
        r=risk_free_rate,
        flag=df['type'],
        return_as='numpy',
        on_error='ignore'
    )

    # Calculate Greeks based on that IV
    greeks_df = get_all_greeks(
        flag=df['type'],
        S=df['underlying_price'],
        K=df['strike'],
        t=df['T'],
        r=risk_free_rate,
        sigma=df['iv'],
        model='black_scholes',
        return_as='dataframe'
    )

    return pd.concat([df, greeks_df], axis=1)

# --- TEST WITH MOCK DATA ---
if __name__ == "__main__":
    # Simulate a TradeStation API response for a 30-Day Option
    # Scenario: SPY is at $590. You buy a $600 Call expiring in 30 days.
    # Notice the price ($5.50) is similar to our 0DTE example, but the STRIKE is further away.
    
    mock_api_response = {
        "StrikePrice": "600",
        "OptionType": "Call",
        "LastPrice": "5.50",
        "UnderlyingPrice": "590.00",
        "ExpirationDate": "2025-12-20" # 30 days from now (approx)
    }

    print("--- Processing 30DTE Trade ---")
    df = adapter_swing_trade(mock_api_response)
    result = calculate_greeks_30dte(df)
    
    # We display VEGA here because for 30DTE, Vega is critical.
    print(result[['expiry_date', 'iv', 'delta', 'gamma', 'vega', 'theta']])