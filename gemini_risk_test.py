import google.generativeai as genai
import yfinance as yf
import pandas as pd
import os

# --- CONFIGURATION ---
# 1. Get your API Key here: https://aistudio.google.com/app/apikey
# 2. Paste it below inside the quotes
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")

# 3. Choose a ticker to test
TICKER = "NVDA" 

# 4. Model Selection (Updated for late 2025)
# If this fails, the script will list available models for you.
MODEL_NAME = 'gemini-2.5-flash' 

# --- SETUP GEMINI ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

def fetch_market_data(ticker):
    """
    Fetches the last 30 days of 1-hour data and calculates a simple RSI.
    """
    print(f"📉 Fetching data for {ticker}...")
    stock = yf.Ticker(ticker)
    # Get 1 month of 1-hour data to simulate a swing trade timeframe
    df = stock.history(period="1mo", interval="1h")
    
    if df.empty:
        raise ValueError("No data found for ticker.")

    # Calculate a simple Relative Strength Index (RSI) for context
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['RSI'] = 100 - (100 / (1 + rs))

    # Keep only the columns Gemini needs to see
    df_clean = df[['Close', 'Volume', 'RSI']].tail(15) # Only send last 15 candles to save tokens
    return df_clean

def analyze_with_gemini(data_snapshot, ticker):
    """
    Sends the data to Gemini with a specific 'Risk Manager' persona.
    """
    print(f"🤖 Consulting Gemini Risk Manager ({MODEL_NAME})...")
    
    # This is the "Thesis" you would typically load from a file
    my_thesis = f"""
    POSITION: LONG LEAPS (Calls) on {ticker}
    ENTRY PRICE: $120.00
    THESIS: Bullish on AI infrastructure spending.
    INVALIDATION: If price closes below $115 OR RSI stays above 80 for 3 candles (Overbought).
    """

    # Construct the prompt
    prompt = f"""
    You are a strict Financial Risk Manager. You do not predict the future; you analyze current structure.
    
    MY TRADE DETAILS:
    {my_thesis}

    CURRENT MARKET DATA (Last 15 hours):
    {data_snapshot.to_string()}

    TASK:
    Analyze the recent price action and RSI. 
    1. Is my invalidation level ($115) currently threatened?
    2. Is the RSI signaling I should take profit (Overbought > 80)?
    3. STATUS: Respond with "HOLD", "WARNING", or "EXIT".
    
    Keep the response concise (under 100 words).
    """

    response = model.generate_content(prompt)
    return response.text

def list_available_models():
    """
    Troubleshooting helper: Lists models available to this API key
    if the default model name is wrong.
    """
    print("\n⚠️ MODEL ERROR DETECTED. Listing available models for your API Key...")
    print("-" * 30)
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                print(f"✅ {m.name}")
        print("-" * 30)
        print("👉 Copy one of the names above (e.g., 'models/gemini-1.5-flash')")
        print("   and paste it into the MODEL_NAME variable at the top of the script.")
    except Exception as e:
        print(f"Could not list models. Error: {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    try:
        # 1. Get Data
        data = fetch_market_data(TICKER)
        
        # 2. Get Analysis
        analysis = analyze_with_gemini(data, TICKER)
        
        # 3. Show Result
        print("-" * 50)
        print(f"REPORT FOR {TICKER}:")
        print("-" * 50)
        print(analysis)
        print("-" * 50)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        # If the error is a 404/Not Found, run the troubleshooter
        if "404" in str(e) or "not found" in str(e).lower():
            list_available_models()
