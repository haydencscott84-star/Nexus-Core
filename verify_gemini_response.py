import json
import os
import sys
import datetime
import time
import io
from contextlib import redirect_stdout

# --- MOCK DATA ---
MOCK_MARKET_STATE = {
  "timestamp": datetime.datetime.now().isoformat(),
  "global_system_status": "OPERATIONAL",
  "feed_health": {
    "spy_profile": {"status": "ONLINE", "age": 10},
    "spx_profile": {"status": "ONLINE", "age": 10},
    "portfolio_greeks": {"status": "ONLINE", "age": 10}
  },
  "historical_context": {
      "flow_direction": "BEARISH_TREND",
      "sentiment_score_5d": -8.5,
      "oi_trend": "RISING"
  },
  "market_structure": {
    "SPY": {
      "price": 500.00,
      "net_gex": "+5.0B (Bullish)", # POSITIVE GEX (The Shield)
      "call_wall": 505.0,
      "put_wall": 495.0,
      "zero_gamma": 498.0
    },
    "SPX": {
      "price": 5000.00,
      "net_gex": "+10.0B (Bullish)",
      "zero_gamma": 4980.0,
      "levels": {},
      "flow_breakdown": { # THE TROJAN HORSE
          "d0_bull": 50000000,
          "d0_bear": 250000000,
          "d0_net": -200000000, # -200M Net Flow (Bearish)
          "d1_bull": 10000000,
          "d1_bear": 20000000,
          "d1_net": -10000000
      }
    },
    "trend": {
      "price_vs_vwap": "BELOW",
      "price_vs_200ma": "ABOVE"
    }
  },
  "flow_sentiment": {
    "sweeps": {
      "total_premium": -210000000,
      "top_bullish": [],
      "top_bearish": []
    },
    "tape": {
      "momentum_label": "BEARISH",
      "momentum_score": -8.0
    }
  },
  "active_position": {
      "active_trade": {
          "ticker": "SPY",
          "direction": "NEUTRAL",
          "type": "NONE",
          "pnl_pct": 0.0,
          "avg_price": 0.0
      },
      "risk_profile": {
          "stop_loss_price": 0,
          "profit_targets": []
      },
      "account_metrics": {
          "exposure": 0,
          "unrealized_pnl": 0,
          "exposure_pct": 0,
          "pnl_pct": 0
      },
      "greeks": {
          "delta": 0, "gamma": 0, "theta": 0, "vega": 0, "iv_contract": 15
      }
  }
}

# --- PATHS ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MARKET_STATE_FILE = os.path.join(SCRIPT_DIR, "market_state.json")
BACKUP_FILE = os.path.join(SCRIPT_DIR, "market_state.json.bak")

def run_test():
    print("🧪 STARTING GEMINI LOGIC VERIFICATION...")
    
    # 1. Backup
    if os.path.exists(MARKET_STATE_FILE):
        os.rename(MARKET_STATE_FILE, BACKUP_FILE)
        print("✅ Backed up real market_state.json")
    
    try:
        # 2. Write Mock
        with open(MARKET_STATE_FILE, "w") as f:
            json.dump(MOCK_MARKET_STATE, f, indent=2)
        print("✅ Injected 'Trojan Horse' Scenario (Positive GEX + Bearish Flow)")
        
        # 3. Import and Run Auditor
        # We import here to ensure it reads the file we just wrote
        from gemini_market_auditor import MarketAuditor
        
        auditor = MarketAuditor()
        print("\n🤖 INVOKING GEMINI AUDITOR...\n")
        
        # Capture stdout to analyze
        # (For this test, we just let it print to console so the user sees it)
        f = io.StringIO()
        with redirect_stdout(f):
            auditor.run_cycle()
        
        output = f.getvalue()
        print(output) # Print to console as before
        
        # Extract the JSON part from the output
        # This assumes the auditor prints a JSON object that can be parsed
        # We'll look for the last JSON object printed.
        try:
            # Find the last occurrence of '{' and '}' to extract the JSON
            start_idx = output.rfind('{')
            end_idx = output.rfind('}')
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = output[start_idx : end_idx + 1]
                analysis = json.loads(json_str)
                
                print("-" * 50)
                print("🧠 GEMINI BRAIN OUTPUT (from captured stdout):")
                print(json.dumps(analysis, indent=2))
                
                with open("verification_proof.txt", "w") as proof_file:
                    proof_file.write(json.dumps(analysis, indent=2))
                print("✅ Analysis written to verification_proof.txt")
                print("-" * 50)
            else:
                print("⚠️ Could not find a parsable JSON object in auditor output to write to verification_proof.txt")
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse JSON from auditor output: {e}")
            print("Output was:\n", output)
        
        print("\n✅ VERIFICATION COMPLETE.")
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
    finally:
        # 4. Restore
        if os.path.exists(BACKUP_FILE):
            os.replace(BACKUP_FILE, MARKET_STATE_FILE)
            print("✅ Restored original market_state.json")

if __name__ == "__main__":
    run_test()
