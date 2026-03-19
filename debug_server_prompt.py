
import os
import json
import logging
import traceback

def safe_read_json(filepath):
    try:
        with open(filepath, "r") as f: return json.load(f)
    except: return {}

# Mock fmt_money to match Auditor
def fmt_money(val):
    if not isinstance(val, (int, float)): return str(val)
    abs_val = abs(val)
    if abs_val >= 1_000_000_000: return f"${val/1_000_000_000:.2f}b"
    elif abs_val >= 1_000_000: return f"${val/1_000_000:.2f}m"
    return f"${val:.2f}"

def label_sent(score):
    if isinstance(score, str): return score
    try:
        if score > 5: return f"BULLISH (+{score})"
        if score < -5: return f"BEARISH ({score})"
        return f"NEUTRAL ({score})"
    except: return str(score)

# Load Real Data
base_dir = os.path.dirname(os.path.abspath(__file__))
state = safe_read_json(os.path.join(base_dir, "market_state.json"))
history = safe_read_json(os.path.join(base_dir, "nexus_history.json"))
sweeps = safe_read_json(os.path.join(base_dir, "nexus_sweeps_v2.json"))

# Extract Vars (Simulate Auditor Logic)
active_pos = state.get("active_position", {})
metrics = active_pos.get("account_metrics", {})

# Sanitizer
def safe_float(v):
    try: return float(v)
    except: return 0.0

acct_val = safe_float(metrics.get("equity", 0))
acct_pnl = safe_float(metrics.get("unrealized_pnl", 0))
acct_exp = safe_float(metrics.get("exposure", 0))
acct_exp_pct = safe_float(metrics.get("exposure_pct", 0))

pos_pnl_pct = safe_float(active_pos.get("pnl_pct", 0.0))
entry_price = safe_float(active_pos.get("avg_price", 0.0))
direction = "NEUTRAL"
ticker = "SPY"

print(f"DEBUG VARS: PnL={acct_pnl}, PnL%={pos_pnl_pct}")

# Magnets
magnets_context = "Magnets"

# Prompt Test
try:
    print("Testing Part 1 (Price)...")
    p1 = f"Account P/L: ${acct_pnl:.2f}"
    print("Part 1 OK")
    
    print("Testing Part 2 (Pos PnL)...")
    p2 = f"Current P/L: {pos_pnl_pct:+.2f}%"
    print("Part 2 OK")
    
    print("Testing Part 3 (Full Prompt)...")
    prompt = f'''
    HOLDINGS CONTEXT:
    Account Value: ${acct_val:,.2f}
    Account P/L: ${acct_pnl:.2f} (Unrealized)
    Account Exposure: ${acct_exp:,.2f} ({acct_exp_pct:.1f}%)

    LIVE POSITION CONTEXT:
    We are holding {direction} on {ticker} from ${entry_price:.2f}. 
    Current P/L: {pos_pnl_pct:+.2f}%.
    '''
    print("Part 3 OK")
    
except Exception as e:
    print(f"CRASH: {e}")
    traceback.print_exc()
