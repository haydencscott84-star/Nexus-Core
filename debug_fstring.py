
import json

# Dummy Vars from Auditor
trend_instruction = "Buy"
spy_price = "UNKNOWN"
tape_mom = "Neutral"
stack_status = "OK"
extension = "NONE"
vwap = "N/A"
sma_20 = "N/A"
sma_50 = "N/A"
sma_200 = "N/A"
gex_framework = "GEX..."
spy = {}
spx_pain = "4000"
spy_0dte_val = 0
spy_prof_delta = 0
d0_net = 0
d1_net = 0
delta_3dte = 0
delta_0dte = 0
sweeps_prem = 0
spy_0dte_sent = 0
spy_next_sent = 0
spy_cum = 0
spy_sw_sent = 0
spx_d0_sent = 0
spx_cum = 0
spx_sw_sent = 0

def fmt_money(v): return "100M"
def label_sent(v): return "SENT"

quant_context = '{"a": 1}'
risk_profiles = {"profile": "cautious"}
acct_val = 0.0
acct_pnl = 0.0
acct_exp = 0.0
acct_exp_pct = 0.0
direction = "LONG"
ticker = "SPY"
entry_price = 0.0
pos_pnl_pct = 0.0
hedge_context = ""
spread_context = ""
magnets_context = "Magnet 1"

try:
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
    3. SPX STRUCTURAL FRAMEWORK (0DTE vs Next):
       {gex_framework}
       
    4. STRUCTURE (GEX LEVELS): 
       - Magnet: {spy.get('vol_trigger', 'N/A')}
       - Call Wall: {spy.get('call_wall', 'N/A')}
       - Put Wall: {spy.get('put_wall', 'N/A')}
       - Max Pain: {spx_pain}
    5. MONEY FLOW ANALYTICS (GRANULAR NET DELTA):
       --------------------------------------------------
       A. SPY PROFILER (The ETF Itself):
          - 0DTE Flow: {fmt_money(spy_0dte_val)}
          - Total Flow: {fmt_money(spy_prof_delta)}
       
       B. SPX PROFILER (The Index):
          - 0DTE Flow: {fmt_money(d0_net)}
          - Next Expiry Flow: {fmt_money(d1_net)}
       
       C. SWEEPS V2 (Smart Money):
          - 3DTE+ (Strategic): {fmt_money(delta_3dte)}
          - 0DTE (Tactical): {fmt_money(delta_0dte)}
          - Total Premium: {fmt_money(sweeps_prem)}
       --------------------------------------------------
       INTERPRETATION: 
       - Convergence (All Green/Red) = STRONG SIGNAL. 
       - Divergence (SPY Green, SPX Red) = CHOP/HEDGING.

    5. SENTIMENT (BREADTH - TRADER CONVICTION):
       * Definition: "Sentiment" tracks the COUNT of Bullish vs Bearish Tags.
       * "Instant": 5-minute snapshot of aggression.
       * "Cumulative": Day-long accumulation of conviction.
       
       * SPY 0DTE Sentiment (Inst): {label_sent(spy_0dte_sent)}
       * SPY Trend Sentiment (Inst): {label_sent(spy_next_sent)}
       * [NEW] SPY CUMULATIVE: {label_sent(spy_cum)}
       * [NEW] SPY SWEEPS FEED: {label_sent(spy_sw_sent)} (Raw Flow Count)
       
       * SPX 0DTE Sentiment (Inst): {label_sent(spx_d0_sent)}
       * [NEW] SPX CUMULATIVE: {label_sent(spx_cum)}
       * [NEW] SPX SWEEPS FEED: {label_sent(spx_sw_sent)} (Raw Flow Count)

       INTERPRETATION LOGIC (DIVERGENCE):
       - IF Cumulative is HIGH (+50) but Net Premium is NEGATIVE: Retail is buying the dip, Whales are selling. (Distribution).
       - IF Cumulative is LOW (-50) but Net Premium is POSITIVE: Retail is panic selling, Whales are absorbing. (Accumulation).
       - IF Cumulative and Premium match: Trend is Healthy.

    6. MARKET STRUCTURE MAGNETS (TIMELINE CONTEXT):
       {magnets_context}
       * INTERPRETATION:
       * These are the strongest Gamma levels in the market.
       * Note the EXPIRATION. 0DTE magnets must be resolved TODAY. Later expiries act as longer-term gravitation.

    7. QUANT RISK VECTORS (NEW):
       {quant_context}
       * Use this to identify if we are in a "WHALE STABILITY" or "RETAIL INSTABILITY" regime.
       * "instability_ratio" > 5.0 indicates high probability of a squeeze or move.
    
    GREEK PROFILING & RECOMMENDATION PROTOCOL (NEW)
    Objective: Compare the user's CURRENT Portfolio Greeks against the OPTIMAL Greeks based on market condition.
    
    Available Profiles:
    {json.dumps(risk_profiles, indent=2)}
    
    Step 1: Diagnose Market Sentiment
    Select ONE profile from the list above that best matches the current environment (e.g., "BEARISH > cautious_top").
    
    Step 2: Perform Gap Analysis
    - Delta Gap: User Net Delta vs Target Delta.
    - Gamma Gap: User Net Gamma vs Target Gamma.
    
    Step 3: Generate Recommendation
    Prescribe a specific action from the "strategy" field of the selected profile.
    
    Step 4: Formulate the Fix
    When generating the "Actionable Fix", you MUST prefix the recommendation with the numeric targets from the selected profile.
    * Format: `[Target Delta: x to y | Target Gamma: x to y] -> Recommendation`

    TRAP ANALYSIS CROSS-CHECK PROTOCOL (NEW)
    Step 1: Analyze Trapped Positioning
    - TRAPPED BEARS: Potential Buying Pressure (Squeeze Fuel). Bias: BULLISH.
    - TRAPPED BULLS: Potential Selling Pressure (Liquidation). Bias: BEARISH.
    
    Step 2: Compare Traps vs Greek Profile
    Step 3: If Divergent, Issue WARNING.
    
    ANALYSIS PROTOCOL:
    - CONFLICT RESOLUTION: If Price is Rising but Flow is Bearish, check the TECHNICALS. If Price > VWAP, the Flow is likely Hedging.
    - GREEK TRANSLATION: Explain the mechanics. (e.g. "High Theta requires velocity").
    - TRAP DETECTION: Who is underwater? Bulls or Bears?
    - HEDGE CONTEXT: If Ticker is 'HEDGED_PORTFOLIO', treat it as a unified SPY position for Greek Gap analysis.
    
    HOLDINGS CONTEXT:
    Account Value: ${acct_val:,.2f}
    Account P/L: ${acct_pnl:.2f} (Unrealized)
    Account Exposure: ${acct_exp:,.2f} ({acct_exp_pct:.1f}%)

    LIVE POSITION CONTEXT:
    We are holding {direction} on {ticker} from ${entry_price:.2f}. 
    Current P/L: {pos_pnl_pct:+.2f}%.
    {hedge_context}
    
    {spread_context}
    
    OUTPUT FORMAT (JSON ONLY)
    {{
      "market_regime": "One of: RALLY, SELLOFF, CHOP, REVERSAL_UP, REVERSAL_DOWN",
      "primary_driver": "What is moving the market?",
      "market_diagnosis": "Must match a key from 'greek_calibration_profiles' (e.g., 'range_chop')",
      "trap_check": "Brief analysis of trapped traders vs profile.",
      "greek_gap": {{
         "delta_status": "Brief status (e.g., OVER_EXPOSED)",
         "gamma_status": "Brief status (e.g., FRAGILITY_RISK)"
      }},
      "key_friction_levels": "Where will price stall?",
      "narrative": "A 2-3 sentence breakdown logic.",
      "action": "HOLD | HEDGE | CLOSE_IMMEDIATELY",
      "actionable_fix": "[Target Delta: min to max | Target Gamma: min to max] -> Specific strategy recommendation to bridge the gap",
      "win_probability": "0-100%",
      "primary_threat": "The single biggest risk factor"
    }}
    '''
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
