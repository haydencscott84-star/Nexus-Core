import sys
import os
import json
import random

# Mock the Model
class MockResponse:
    def __init__(self, text):
        self.text = text

class MockModel:
    def generate_content(self, prompt, **kwargs):
        print("\n--- PROMPT SENT TO GEMINI ---")
        print(prompt) # Print the prompt so we can inspect the numeric inputs
        print("-----------------------------\n")
        
        # Simulate a GOOD response with specific prices
        return MockResponse('''
        ```json
        {
          "market_regime": "CHOP",
          "primary_driver": "Dealer Gamma Pinning",
          "key_friction_levels": "Resistance at Put Wall ($5850) and VWAP ($5815)",
          "anomaly_detection": "None",
          "narrative": "Price is currently pinned between the Call Wall ($5900) and the Put Wall ($5850). We are seeing a rejection of VWAP ($5815) suggesting bears are defending.",
          "action": "HOLD",
          "win_probability": "60%",
          "primary_threat": "Break below $5800"
        }
        ```
        ''')

# Mock Variables
direction = "LONG"
ticker = "SPY"
entry_price = 580.00
pos_pnl_pct = 0.5
spy_price = 582.50
tape_mom = "Neutral"
stack_status = "Bullish"
extension = "Normal"
vwap = 581.50
sma_20 = 579.00
sma_50 = 575.00
sma_200 = 560.00
spy = {'vol_trigger': 5800, 'call_wall': 5900, 'put_wall': 5800}
spx_pain = 5850
sweeps_prem = 1500000
d0_net = -500000
d1_net = 2000000
trend_instruction = "MECHANICAL STATE: STANDARD."

print("--- TESTING PROMPT CONSTRUCTION ---")

# --- REPLICATING THE LOGIC FROM gemini_market_auditor.py (Lines 340+) ---
prompt = f'''
SYSTEM PROMPT:
You are a Senior Market Structure Analyst. 
Your goal is NOT to advise on buying/selling. 
Your goal is to EXPLAIN the mechanics driving the current price action.

INSTRUCTION:
{trend_instruction}
CRITICAL: YOU MUST CITE SPECIFIC PRICE LEVELS. Do not say "at the wall", say "at the Call Wall ($5850)". Do not say "above VWAP", say "above VWAP ($5815)".

DATA INGESTION:
1. PRICE: ${spy_price} (Trend Context: {tape_mom})
2. TECHNICAL STRUCTURE:
   - Stack: {stack_status} ({extension})
   - Key Levels: VWAP ${vwap} | SMA20 ${sma_20} | SMA50 ${sma_50} | SMA200 ${sma_200}
3. STRUCTURE (GEX): 
   - Magnet: {spy.get('vol_trigger', 'N/A')}
   - Call Wall: {spy.get('call_wall', 'N/A')}
   - Put Wall: {spy.get('put_wall', 'N/A')}
   - Max Pain: {spx_pain}
4. FLOW: 
   - Net Premiums: ${sweeps_prem:,.0f}
   - SPX 0DTE Flow: ${d0_net:,.0f} (Tactical)
   - SPX 3DTE+ Flow: ${d1_net:,.0f} (Strategic)

ANALYSIS PROTOCOL:
- CONFLICT RESOLUTION: If Price is Rising but Flow is Bearish, check the TECHNICALS. If Price > VWAP, the Flow is likely Hedging.
- GREEK TRANSLATION: Explain the mechanics. (e.g. "High Theta requires velocity").
- TRAP DETECTION: Who is underwater? Bulls or Bears?

LIVE POSITION CONTEXT:
We are holding {direction} on {ticker} from ${entry_price:.2f}. 
Current P/L: {pos_pnl_pct:+.2f}%.

OUTPUT FORMAT (JSON):
{{
  "market_regime": "SHORT_SQUEEZE | LIQUIDATION | CHOP | BREAKOUT",
  "primary_driver": "What is moving the price? (e.g. 'Dealer Gamma Hedging', 'Real Money Selling', '0DTE Speculation')",
  "key_friction_levels": "Where will price likely stop/stall? (Based on GEX/Walls/SMAs)",
  "anomaly_detection": "Is anything weird? (e.g. Price up on Put Flow)",
  "narrative": "A 2-3 sentence breakdown. YOU MUST INCLUDE SPECIFIC PRICES (e.g. '$5800 Put Wall'). Explain the mechanics.",
  "action": "HOLD | HEDGE | CLOSE_IMMEDIATELY",
  "win_probability": "0-100%",
  "primary_threat": "The single biggest risk factor right now"
}}
'''

model = MockModel()
response = model.generate_content(prompt)
print("SUCCESS: Prompt Generated.")
