import json
import os
import sys
from unittest.mock import MagicMock

# Mock dependencies
sys.modules['nexus_lock'] = MagicMock()
sys.modules['google.generativeai'] = MagicMock()

# Import the auditor (after mocking)
# We need to temporarily rename the file or just import it and monkeypatch
# But since it runs code on import (nexus_lock), we mocked it.
import gemini_market_auditor

def test_gex_vision():
    print("🧪 TEST: Verifying Gemini GEX Vision (SPX vs SPY)...")
    
    # 1. Mock Market State with Divergence
    # SPX = Bullish (+), SPY = Bearish (-)
    mock_state = {
        "global_system_status": "OPERATIONAL",
        "market_structure": {
            "SPY": {
                "price": 600.00,
                "net_gex": "-$500M (Bearish)",
                "call_wall": 605.00,
                "put_wall": 595.00,
                "zero_gamma": 600.00,
                "vol_trigger": 602.50
            },
            "SPX": {
                "spx_price": 6000.00,
                "net_gex": "+$2.0B (Bullish)",
                "zero_gamma_level": 6000.00,
                "major_levels": {}
            }
        },
        "flow_sentiment": {
            "tape": {"momentum_label": "NEUTRAL"}
        },
        "historical_context": {},
        "feed_health": {}
    }
    
    # Write to temp file
    with open("market_state_test.json", "w") as f:
        json.dump(mock_state, f)
        
    # Mock spy_thesis.json
    mock_thesis = {
        "macro_structure_SPX": {"definition": "The Fortress"},
        "micro_structure_SPY": {"definition": "The Skirmish"}
    }
    with open("spy_thesis_test.json", "w") as f:
        json.dump(mock_thesis, f)
        
    # Monkeypatch the file path in the module
    gemini_market_auditor.MARKET_STATE_FILE = "market_state_test.json"
    gemini_market_auditor.THESIS_FILE = "spy_thesis_test.json" # Note: Variable name in module is thesis_path inside run_cycle, so we can't easily patch it unless we patch os.path.join or the variable itself if it was global.
    # Wait, thesis_path is local to run_cycle. I can't patch it easily.
    # However, I can write to the actual "spy_thesis.json" in the current directory if the script looks there?
    # The script uses os.path.dirname(__file__).
    # Since I'm running the test in the same dir, I can just backup the real one and write a temp one?
    # Or better, I can rely on the real spy_thesis.json since I just updated it!
    # Yes, I will use the REAL spy_thesis.json for this test since I modified it.
    
    # Mock the model.generate_content to capture the prompt
    mock_model = MagicMock()
    gemini_market_auditor.model = mock_model
    
    # Run the cycle
    auditor = gemini_market_auditor.MarketAuditor()
    auditor.run_cycle()
    
    # Extract the prompt sent to Gemini
    call_args = mock_model.generate_content.call_args
    if not call_args:
        print("❌ TEST FAILED: No call to Gemini model.")
        return

    prompt = call_args[0][0]
    
    # Verify GEX presence
    print("\n--- CAPTURED PROMPT SECTION ---")
    if "GEX HIERARCHY (NEW PROTOCOL)" in prompt:
        print("✅ GEX HIERARCHY Found")
    else:
        print("❌ GEX HIERARCHY Missing")
        
    if "GEX DIVERGENCE PROTOCOL" in prompt:
        print("✅ GEX DIVERGENCE PROTOCOL Found")
    else:
        print("❌ GEX DIVERGENCE PROTOCOL Missing")

    if "Dealer GEX (SPY): -$500M (Bearish)" in prompt and "Dealer GEX (SPX): +$2.0B (Bullish)" in prompt:
        print("✅ SUCCESS: Gemini is seeing both SPY (Bearish) and SPX (Bullish) GEX profiles.")
    else:
        print("❌ FAILURE: Prompt does not contain distinct GEX values.")

    # Cleanup
    if os.path.exists("market_state_test.json"):
        os.remove("market_state_test.json")
    if os.path.exists("spy_thesis_test.json"):
        os.remove("spy_thesis_test.json")

if __name__ == "__main__":
    test_gex_vision()
