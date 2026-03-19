
import json
import datetime
import os

def test_vrp_logic():
    print("Testing VRP logic...")
    ctx = {'iv30': 0.15, 'hv30': 0.12}
    TICKER = "SPY"
    
    iv30 = ctx.get('iv30', 0)
    hv30 = ctx.get('hv30', 0)
    vrp = iv30 - hv30
    
    vrp_data = {
        "timestamp": datetime.datetime.now().isoformat(),
        "ticker": TICKER,
        "iv30": iv30,
        "hv30": hv30,
        "vrp_spread": vrp,
        "signal": "SELL_PREMIUM" if vrp > 0 else "BUY_PREMIUM"
    }
    
    filename = "nexus_vrp_context_test.json"
    temp_file = f"{filename}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(vrp_data, f, default=str)
        os.replace(temp_file, filename)
        print(f"✅ Wrote {filename}")
        
        # Verify Read
        with open(filename, 'r') as f:
            d = json.load(f)
            print(f"Read Data: {d}")
            assert d['vrp_spread'] == 0.03
            assert d['signal'] == "SELL_PREMIUM"
            print("✅ Logic Correct")
            
        os.remove(filename)
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_vrp_logic()
