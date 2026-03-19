import json
import os
import time
import market_bridge

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SWEEPS_FILE = os.path.join(SCRIPT_DIR, "nexus_sweeps.json")
SPY_PROFILE_FILE = os.path.join(SCRIPT_DIR, "nexus_spy_profile.json")
SPX_PROFILE_FILE = os.path.join(SCRIPT_DIR, "nexus_spx_profile.json")
TAPE_FILE = os.path.join(SCRIPT_DIR, "nexus_tape.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "market_state.json")

def create_mock_data():
    """
    Creates dummy JSON files with edge cases.
    """
    print("Creating mock data...")
    
    # 1. Sweeps (Normal)
    sweeps_data = {
        "total_premium": 15000000,
        "bullish_flow_list": [{"ticker": "SPY", "prem": 100000}] * 5, # Should be truncated to 3
        "bearish_flow_list": []
    }
    with open(SWEEPS_FILE, "w") as f: json.dump(sweeps_data, f)

    # 2. SPY Profile (Bearish GEX)
    spy_data = {
        "current_price": 450.50,
        "net_gex": -3500000000, # Should be "-3.5B (Bearish)"
        "call_wall": 460,
        "put_wall": 440
    }
    with open(SPY_PROFILE_FILE, "w") as f: json.dump(spy_data, f)

    # 3. SPX Profile (Missing Fields)
    spx_data = {
        "spx_price": 4505.00
        # Missing zero_gamma and major_levels
    }
    with open(SPX_PROFILE_FILE, "w") as f: json.dump(spx_data, f)

    # 4. Tape (Strong Buy Momentum)
    tape_data = {
        "tape_momentum_score": 8.5, # Should be "STRONG_BUY_SIDE"
        "last_size": 500
    }
    with open(TAPE_FILE, "w") as f: json.dump(tape_data, f)

def verify_output():
    """
    Checks if market_state.json exists and contains expected values.
    """
    print("Verifying output...")
    
    if not os.path.exists(OUTPUT_FILE):
        print("❌ FAILED: market_state.json not found.")
        return

    with open(OUTPUT_FILE, "r") as f:
        data = json.load(f)

    # Assertions
    try:
        # Check GEX Formatting
        gex = data["market_structure"]["SPY"]["net_gex"]
        assert gex == "-3.5B (Bearish)", f"GEX Format Mismatch: {gex}"
        
        # Check Momentum Label
        mom = data["flow_sentiment"]["tape"]["momentum_label"]
        assert mom == "STRONG_BUY_SIDE", f"Momentum Label Mismatch: {mom}"
        
        # Check List Truncation
        bull_len = len(data["flow_sentiment"]["sweeps"]["top_bullish"])
        assert bull_len == 3, f"List Truncation Failed: {bull_len}"
        
        # Check Missing Data Handling (SPX)
        zero_gamma = data["market_structure"]["SPX"]["zero_gamma"]
        assert zero_gamma == 0, f"Missing Data Default Failed: {zero_gamma}"

        print("✅ BRIDGE LOGIC PASSED")

    except AssertionError as e:
        print(f"❌ FAILED: {e}")
    except Exception as e:
        print(f"❌ ERROR: {e}")

def main():
    try:
        create_mock_data()
        market_bridge.run_bridge_cycle()
        verify_output()
    except Exception as e:
        print(f"❌ TEST SUITE ERROR: {e}")
    finally:
        # Cleanup (Optional - keep for inspection)
        pass

if __name__ == "__main__":
    main()
