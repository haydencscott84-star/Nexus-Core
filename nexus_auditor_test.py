import google.generativeai as genai
import os
import json
import datetime

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.5-flash'
MARKET_STATE_FILE = "market_state.json"
THESIS_FILE = "spy_thesis.json"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

def safe_read_json(filepath):
    try:
        with open(filepath, "r") as f: return json.load(f)
    except: return {}

def run_test():
    print("📉 Loading Market State...")
    state = safe_read_json(MARKET_STATE_FILE)
    thesis = safe_read_json(THESIS_FILE)
    thesis_str = json.dumps(thesis, indent=2)
    
    # Extract Data
    mkt = state.get('market_structure', {})
    spy = mkt.get('SPY', {})
    flow = state.get('flow_sentiment', {})
    active_pos = state.get("active_position", {})
    greeks = active_pos.get("greeks", {})
    
    # Construct FULL Prompt
    prompt = f"""
    SYSTEM PROMPT:
    You are a Risk Manager. Mission: Assess market structure and position risk.
    
    MASTER CONSTITUTION (LOGIC CORE):
    {thesis_str}
    
    GREEK ANALYSIS PROTOCOL:
    1. Theta Check: Daily Theta Cost is {greeks.get('theta')}. If > $50/day and DTE > 30, ROLL OUT.
    2. Delta Integrity: Net Delta is {greeks.get('delta')}. If < -200 for shorts, HOLD.
    3. Vega Risk: IV is {greeks.get('iv_contract')}.
    
    THE FACTS: 
    Retail Price: ${spy.get('price')} 
    Dealer GEX: {spy.get('net_gex')}
    Structure: Call Wall ${spy.get('call_wall')} | Put Wall ${spy.get('put_wall')} | Zero Gamma ${spy.get('zero_gamma')}
    
    LIVE POSITION:
    {active_pos.get('qty')}x {active_pos.get('active_trade', {}).get('ticker')} {active_pos.get('active_trade', {}).get('type')}
    Greeks: Delta:{greeks.get('delta')} | Gamma:{greeks.get('gamma')} | Theta:{greeks.get('theta')} | Vega:{greeks.get('vega')}
    
    INSTRUCTION:
    Analyze the risk given the GEX Walls and Greeks.
    
    OUTPUT JSON:
    {{
        "action": "HOLD/HEDGE/CLOSE",
        "primary_threat": "Biggest risk?",
        "reasoning": "Detailed analysis citing GEX walls and Greeks."
    }}
    """
    
    print("🤖 Querying Gemini (Full Detail)...")
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    
    print("\n=== GEMINI RESPONSE ===")
    print(response.text)
    
    with open("gemini_test_result.json", "w") as f:
        f.write(response.text)

if __name__ == "__main__":
    run_test()
