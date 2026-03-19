import json
import os
import time
from datetime import datetime

# Import your actual subsystems
# We wrap this in try/except so the test script doesn't crash if files are missing
try:
    import market_bridge  # The Bridge
except ImportError:
    print("❌ Critical: Could not import 'market_bridge'. Ensure it exists in this folder.")
    exit()

def create_mock_data(scenario_name):
    """
    Generates fake JSON files to simulate specific market conditions.
    """
    print(f"\n🧪 SETTING UP SCENARIO: {scenario_name}")
    print("-" * 40)

    # SCENARIO: "THE BULL TRAP"
    # Price is rising (Retail Bullish), but GEX is Negative (Institutional Bearish).
    
    # 1. Mock Portfolio (Long Call)
    portfolio = {
        "ticker": "SPY",
        "direction": "BULLISH", # We are Long
        "status": {"pnl_percent": 12.5, "dte": 45},
        "risk_profile": {"stop_loss_price": 590.00}
    }
    
    # 2. Mock Tape (Retail Buying)
    tape = {
        "script": "ts_nexus",
        "live_data": {"last_price": 598.50, "tape_momentum": 8.5}, # Price going up!
        "structure": {
            "vwap": 596.00,
            "status": "ABOVE_VWAP" # Looks bullish to retail
        }
    }
    
    # 3. Mock SPX Profile (The Trap - Institutional Selling)
    spx = {
        "script": "spx_profiler",
        "net_gex": -2500000000, # Negative $2.5B (BEARISH STRUCTURE)
        "zero_gamma_level": 6000
    }
    
    # 4. Mock Sweeps (Mixed)
    sweeps = {
        "total_premium": 5000000,
        "bullish_flow_list": [
            {
                "ticker": "SPY",
                "parsed_expiry": "2025-01-17",
                "parsed_strike": 600.0,
                "parsed_type": "CALL",
                "total_premium": 1200000,
                "priority_score": 3,
                "priority_notes": "Whale, Aggressive",
                "sentiment_str": "BUY"
            }
        ],
        "bearish_flow_list": [
            {
                "ticker": "SPY",
                "parsed_expiry": "2025-01-17",
                "parsed_strike": 580.0,
                "parsed_type": "PUT",
                "total_premium": 3800000,
                "priority_score": 4,
                "priority_notes": "Whale, Floor Guard",
                "sentiment_str": "SELL"
            }
        ]
    }

    # 5. Mock SPY Profile (Levels)
    spy = {
        "current_price": 598.50,
        "call_wall": 605,
        "put_wall": 590
    }

    # --- DUMP MOCK FILES ---
    with open("nexus_portfolio.json", "w") as f: json.dump(portfolio, f)
    with open("nexus_tape.json", "w") as f: json.dump(tape, f)
    with open("nexus_spx_profile.json", "w") as f: json.dump(spx, f)
    with open("nexus_sweeps.json", "w") as f: json.dump(sweeps, f)
    with open("nexus_spy_profile.json", "w") as f: json.dump(spy, f)
    
    print("✅ Mock Data Generated (Simulating Live Market)")

def run_pipeline():
    """
    Runs the actual Bridge script against the mock data.
    """
    print("🔄 Running Market Bridge...")
    try:
        # Run the bridge logic to create market_state.json
        # Note: If your bridge script uses a different function name, update this call.
        if hasattr(market_bridge, 'update_master_record'):
            market_bridge.update_master_record()
        elif hasattr(market_bridge, 'run_bridge_cycle'):
            market_bridge.run_bridge_cycle()
        elif hasattr(market_bridge, 'normalize_nexus_data'):
             # Fallback if the user is running the main block manually
             data = market_bridge.normalize_nexus_data()
             with open("market_state.json", "w") as f:
                json.dump(data, f, indent=2)
             print(f"✅ Master Record updated manually via test script")
        else:
            print("⚠️ Warning: Could not find 'update_master_record' or 'run_bridge_cycle' in market_bridge.")
            
    except Exception as e:
        print(f"❌ Bridge Failed: {e}")
        return

if __name__ == "__main__":
    # Run the "Bull Trap" simulation
    create_mock_data("THE INSTITUTIONAL TRAP (Long into Negative GEX)")
    
    # Pause to ensure file IO completes
    time.sleep(1)
    
    # Execute the bridge logic
    run_pipeline()
    
    # Validation
    if os.path.exists("market_state.json"):
        print("\n✅ SUCCESS: 'market_state.json' was generated.")
        with open("market_state.json") as f:
            data = json.load(f)
            print(f"   - Timestamp: {data.get('timestamp')}")
            print(f"   - Ticker: {data.get('market_structure', {}).get('SPY', {}).get('price')}")
    else:
        print("\n❌ FAILURE: 'market_state.json' was NOT generated.")
