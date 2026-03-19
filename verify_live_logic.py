import zmq
import json
import time
import os
import datetime

# Configuration
ZMQ_PORT = 5566
PORTFOLIO_FILE = "nexus_portfolio.json"

def get_portfolio_data():
    try:
        with open(PORTFOLIO_FILE, 'r') as f:
            return json.load(f)
    except:
        return None

def run_verification():
    print("🔵 Starting Live Logic Verification...")
    print(f"   Target: trader_dashboard.py (ZMQ Port {ZMQ_PORT})")
    print("   Goal: Prove P/L and Price are dynamic, not hardcoded.")

    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    try:
        socket.bind(f"tcp://*:{ZMQ_PORT}")
        print("✅ Bound to ZMQ Port 5566 (Simulating TradeStation Feed)")
    except zmq.error.ZMQError:
        print("❌ Could not bind to port 5566. Is ts_nexus.py running?")
        print("   Please kill ts_nexus.py to run this verification.")
        return

    # Scenario 1: Initial State
    # Entry: $32.20, Market: $30.00, P/L: -$500
    payload_1 = {
        "total_account_value": 55000.0,
        "unrealized_pnl": -500.0,
        "positions": [
            {
                "Symbol": "SPY 260116P710",
                "Quantity": 3,
                "Last": 30.00,
                "AveragePrice": 32.20,
                "MarketValue": 9000.0,
                "TotalCost": 9660.0,
                "UnrealizedProfitLoss": -660.0,
                "OpenProfitLossPercent": -6.83,
                "ExpirationDate": "2026-01-16T00:00:00Z"
            }
        ]
    }

    print("\n📡 Sending Scenario 1: Market Price $30.00 (P/L -6.83%)")
    for _ in range(5): # Send multiple times to ensure receipt
        socket.send_multipart([b"A", json.dumps(payload_1).encode('utf-8')])
        time.sleep(0.5)

    time.sleep(2) # Wait for dashboard to write file
    
    data_1 = get_portfolio_data()
    if data_1:
        pnl_1 = data_1['active_trade']['pnl_pct']
        entry_1 = data_1['active_trade']['avg_price']
        print(f"   🔍 Dashboard Output: Entry ${entry_1} | P/L {pnl_1}%")
    else:
        print("   ❌ Dashboard did not write nexus_portfolio.json")

    # Scenario 2: Market Moves Against Us
    # Entry: $32.20, Market: $28.00, P/L: Increased Loss
    payload_2 = {
        "total_account_value": 54000.0,
        "unrealized_pnl": -1500.0,
        "positions": [
            {
                "Symbol": "SPY 260116P710",
                "Quantity": 3,
                "Last": 28.00,
                "AveragePrice": 32.20,
                "MarketValue": 8400.0,
                "TotalCost": 9660.0,
                "UnrealizedProfitLoss": -1260.0,
                "OpenProfitLossPercent": -13.04,
                "ExpirationDate": "2026-01-16T00:00:00Z"
            }
        ]
    }

    print("\n📡 Sending Scenario 2: Market Price $28.00 (P/L -13.04%)")
    for _ in range(5):
        socket.send_multipart([b"A", json.dumps(payload_2).encode('utf-8')])
        time.sleep(0.5)

    time.sleep(2)

    data_2 = get_portfolio_data()
    if data_2:
        pnl_2 = data_2['active_trade']['pnl_pct']
        entry_2 = data_2['active_trade']['avg_price']
        print(f"   🔍 Dashboard Output: Entry ${entry_2} | P/L {pnl_2}%")
        
        if pnl_1 != pnl_2:
            print("\n✅ SUCCESS: P/L updated dynamically based on feed input.")
            print("   This proves NO HARDCODED MATH is being used.")
        else:
            print("\n❌ FAILURE: P/L did not change.")

if __name__ == "__main__":
    run_verification()
