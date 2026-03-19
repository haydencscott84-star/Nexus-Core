import json
import datetime

# Test Position: Full Account Metrics & Risk Profile
TEST_POSITION = {
    "script": "trader_dashboard",
    "timestamp": datetime.datetime.now().isoformat(),
    "account_metrics": {
        "exposure": 35500.00,
        "unrealized_pnl": 1250.00,
        "equity": 105000.00
    },
    "active_trade": {
        "ticker": "SPY 260116P710",
        "qty": 50.0,
        "type": "PUT",
        "strike": 710.0,
        "expiry": "2026-01-16",
        "direction": "BEARISH"
    },
    "risk_profile": {
        "stop_loss_price": 610.00,
        "profit_target": 580.00,
        "invalidation_condition": "Full Data Test"
    }
}

FILE = "nexus_portfolio.json"

with open(FILE, "w") as f:
    json.dump(TEST_POSITION, f, indent=4)

print(f"✅ Injected Full Position into {FILE}")
print(f"   Exposure: ${TEST_POSITION['account_metrics']['exposure']} | P/L: ${TEST_POSITION['account_metrics']['unrealized_pnl']}")
print("   Watch gemini_market_auditor.py output now...")
