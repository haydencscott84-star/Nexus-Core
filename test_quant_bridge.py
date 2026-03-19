
import pandas as pd
import json
from quant_bridge import build_quant_payload

print("🔬 TESTING QUANT BRIDGE LOGIC...")

# 1. Create Dummy Data
data = [
    # SPX - Whale Stability (Balanced)
    {'ticker': 'SPX', 'strike': 4500, 'expiry': '2025-12-20', 'status': 'TRAPPED BULLS', 'gamma': 100.0, 'theta': -50.0},
    {'ticker': 'SPX', 'strike': 4400, 'expiry': '2025-12-20', 'status': 'TRAPPED BEARS', 'gamma': 110.0, 'theta': -50.0},
    
    # SPY - Retail Instability (Imbalanced)
    {'ticker': 'SPY', 'strike': 450, 'expiry': '2025-12-20', 'status': 'TRAPPED BULLS', 'gamma': 10.0, 'theta': -10.0},
    # High Bear Gamma for SPY
    {'ticker': 'SPY', 'strike': 440, 'expiry': '2025-12-20', 'status': 'TRAPPED BEARS', 'gamma': 100.0, 'theta': -20.0},
]

df = pd.DataFrame(data)

# 2. Run Function (No magnet price needed)
payload = build_quant_payload(df)

# 3. Print Output
print(json.dumps(payload, indent=2))

# 4. Assertions
analysis = payload['analysis']

print("\n🧪 Validating Logic Rules:")

# SPX Check
spx = analysis['SPX']
print(f"   SPX Regime: {spx['regime']} (Expected: WHALE STABILITY) -> {'Pass' if spx['regime'] == 'WHALE STABILITY' else 'FAIL'}")
# Ratio = 110 / 100 = 1.1
print(f"   SPX Ratio: {spx['risk_vector']['instability_ratio']} (Expected: 1.1) -> {'Pass' if spx['risk_vector']['instability_ratio'] == 1.1 else 'FAIL'}")

# SPY Check
spy = analysis['SPY']
print(f"   SPY Regime: {spy['regime']} (Expected: RETAIL INSTABILITY) -> {'Pass' if spy['regime'] == 'RETAIL INSTABILITY' else 'FAIL'}")
# Ratio = 100 / 10 = 10.0
print(f"   SPY Ratio: {spy['risk_vector']['instability_ratio']} (Expected: 10.0) -> {'Pass' if spy['risk_vector']['instability_ratio'] == 10.0 else 'FAIL'}")

