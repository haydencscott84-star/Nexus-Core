import json
import datetime

# Test Position: 50x SPY Calls (UW Integration Test)
TEST_POSITION = {
    "script": "trader_dashboard",
    "timestamp": datetime.datetime.now().isoformat(),
    "active_trade": {
        "ticker": "SPY",
        "qty": 50.0,
        "type": "CALL",
        "strike": 600.0,
        "expiry": "2025-12-19", # Valid Monthly Expiry
        "direction": "BULLISH"
    },
    "risk_profile": {
        "stop_loss_price": 590.00,
        "profit_target": 620.00,
        "invalidation_condition": "UW Integration Test"
    }
}

FILE = "nexus_portfolio.json"

with open(FILE, "w") as f:
    json.dump(TEST_POSITION, f, indent=4)

print(f"✅ Injected Test Position into {FILE}")
print(f"   {TEST_POSITION['active_trade']['qty']}x {TEST_POSITION['active_trade']['ticker']} {TEST_POSITION['active_trade']['type']} ${TEST_POSITION['active_trade']['strike']} Exp:{TEST_POSITION['active_trade']['expiry']}")
print("   Watch nexus_greeks.py output now...")
