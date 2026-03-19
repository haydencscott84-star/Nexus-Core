import json
import datetime

# Test Position: 50x SPY PUTS (Problematic Ticker Format)
TEST_POSITION = {
    "script": "trader_dashboard",
    "timestamp": datetime.datetime.now().isoformat(),
    "active_trade": {
        "ticker": "SPY 260116P710", # The problematic format
        "qty": 50.0,
        "type": "PUT",
        "strike": 710.0,
        "expiry": "2026-01-16",
        "direction": "BEARISH"
    },
    "risk_profile": {
        "stop_loss_price": 610.00,
        "profit_target": 580.00,
        "invalidation_condition": "Regex Fix Test"
    }
}

FILE = "nexus_portfolio.json"

with open(FILE, "w") as f:
    json.dump(TEST_POSITION, f, indent=4)

print(f"✅ Injected Test Position into {FILE}")
print(f"   {TEST_POSITION['active_trade']['qty']}x {TEST_POSITION['active_trade']['ticker']} {TEST_POSITION['active_trade']['type']} ${TEST_POSITION['active_trade']['strike']} Exp:{TEST_POSITION['active_trade']['expiry']}")
print("   Watch nexus_greeks.py output now...")
