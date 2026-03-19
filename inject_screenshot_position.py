import json
import datetime

# Test Position: Matching User Screenshot
# Header: EXP 18.0%, P/L -1.64%
# Row: SPY 710P, QTY 3, P/L -8.3%, STOP 692.15
# Derived from User Input:
# Qty: 3
# Entry: $32.20
# Cost Basis = 3 * 100 * 32.20 = $9,660.00
# Pos P/L: -8.30%
# Current Value (Exposure) = $9,660 * (1 - 0.083) = $8,858.22
# Equity (derived from 18% exposure) = $8,858.22 / 0.18 = $49,212.33
# Acct P/L (derived from -1.64%) = $49,212.33 * -0.0164 = -$807.08

QTY = 3
ENTRY = 32.20
COST_BASIS = QTY * 100 * ENTRY
POS_PNL_PCT = -0.083

EXPOSURE = COST_BASIS * (1 + POS_PNL_PCT) # $8,858.22
EQUITY = EXPOSURE / 0.18
ACCT_PNL = EQUITY * -0.0164

TEST_POSITION = {
    "script": "trader_dashboard",
    "timestamp": datetime.datetime.now().isoformat(),
    "account_metrics": {
        "exposure": EXPOSURE,
        "unrealized_pnl": ACCT_PNL,
        "equity": EQUITY,
        "exposure_pct": 18.0,
        "pnl_pct": -1.64
    },
    "active_trade": {
        "ticker": "SPY 260116P710", # OCC Format for 710 Put
        "qty": 3.0,
        "type": "PUT",
        "strike": 710.0,
        "expiry": "2026-01-16",
        "direction": "BEARISH",
        "pnl_pct": -8.3,
        "avg_price": 32.20 # Simulated API Value
    },
    "risk_profile": {
        "stop_loss_price": 692.15,
        "profit_target": 678.10, # Legacy T1
        "profit_targets": [678.10, 671.20, 661.80], # T1, T2, T3 from screenshot
        "invalidation_condition": "Screenshot Verification"
    }
}

FILE = "nexus_portfolio.json"

with open(FILE, "w") as f:
    json.dump(TEST_POSITION, f, indent=4)

print(f"✅ Injected Screenshot Data into {FILE}")
print(f"   Exp: {TEST_POSITION['account_metrics']['exposure_pct']}% | Acct P/L: {TEST_POSITION['account_metrics']['pnl_pct']}%")
print(f"   Pos P/L: {TEST_POSITION['active_trade']['pnl_pct']}% | Stop: ${TEST_POSITION['risk_profile']['stop_loss_price']}")
print("   Watch gemini_market_auditor.py output now...")
