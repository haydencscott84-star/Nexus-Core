import json
import datetime

# Test Position: Full Account Metrics with Percentages
TEST_POSITION = {
    "script": "trader_dashboard",
    "timestamp": datetime.datetime.now().isoformat(),
    "account_metrics": {
        "exposure": 18900.00, # 18% of 105k
        "unrealized_pnl": 1680.00, # 1.6% of 105k
        "equity": 105000.00,
        "exposure_pct": 18.0,
        "pnl_pct": 1.6
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
        "invalidation_condition": "Percentage Test"
    }
}

FILE = "nexus_portfolio.json"

with open(FILE, "w") as f:
    json.dump(TEST_POSITION, f, indent=4)

print(f"✅ Injected Percentage Test into {FILE}")
print(f"   Exposure: {TEST_POSITION['account_metrics']['exposure_pct']}% | P/L: {TEST_POSITION['account_metrics']['pnl_pct']}%")
print("   Watch gemini_market_auditor.py output now...")
