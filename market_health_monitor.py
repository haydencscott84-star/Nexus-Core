import yfinance as yf
import json
import os
import time
import datetime
import sys

# --- CONFIG ---
OUTPUT_FILE = "market_health.json"
CONFIG_FILE = "market_config.json"

def safe_read_json(filepath):
    if not os.path.exists(filepath): return {}
    try:
        with open(filepath, "r") as f: return json.load(f)
    except: return {}

def get_config_thresholds():
    config = safe_read_json(CONFIG_FILE)
    limits = config.get("risk_limits", {})
    return {
        "vix_inversion": limits.get("vix_inversion_limit", 1.0),
        "vvix_crash": limits.get("vvix_crash_level", 110),
        "breadth_div": limits.get("breadth_divergence_threshold", 0.01)
    }

def fetch_market_data():
    tickers = ["^VIX", "^VIX3M", "^VVIX", "SPY", "RSP"]
    try:
        # Fetch last 10 days to calculate breadth trend
        data = yf.download(tickers, period="10d", progress=False)['Close']
        
        # Handle Multi-Index columns if necessary (yfinance update)
        if hasattr(data.columns, 'levels'):
            # Flatten or just access by key if possible
            pass
            
        return data
    except Exception as e:
        print(f"❌ Data Fetch Error: {e}")
        return None

def analyze_health():
    print(f"🔍 Starting Market Health Check at {datetime.datetime.now().strftime('%H:%M:%S')}...")
    
    df = fetch_market_data()
    if df is None or df.empty:
        print("⚠️ No Data Fetched.")
        return

    limits = get_config_thresholds()
    
    # Extract Latest Values
    try:
        # yfinance returns a DataFrame. We need the last row.
        last_row = df.iloc[-1]
        
        vix = float(last_row["^VIX"])
        vix3m = float(last_row["^VIX3M"])
        vvix = float(last_row["^VVIX"])
        spy = float(last_row["SPY"])
        rsp = float(last_row["RSP"])
        
        # 1. VIX Term Structure
        vix_ratio = vix / vix3m if vix3m > 0 else 0
        term_structure_status = "NORMAL"
        if vix_ratio > limits["vix_inversion"]:
            term_structure_status = "BACKWARDATION (RISK)"
            
        # 2. Breadth Divergence (10-Day Relative Performance)
        # Calculate % Change over last 10 days (or available data)
        spy_start = float(df["SPY"].iloc[0])
        rsp_start = float(df["RSP"].iloc[0])
        
        spy_perf = (spy - spy_start) / spy_start
        rsp_perf = (rsp - rsp_start) / rsp_start
        
        rel_perf = rsp_perf - spy_perf # Negative means RSP lagging
        
        breadth_status = "STABLE"
        # If SPY is UP but RSP is LAGGING significantly
        if spy_perf > 0 and rel_perf < -limits["breadth_div"]:
            breadth_status = "DIVERGENCE (THIN RALLY)"
            
        # 3. Crash Probability
        crash_status = "LOW"
        if vvix > limits["vvix_crash"]:
            crash_status = "EXTREME TAIL RISK"
            
        # --- DETERMINE REGIME ---
        risk_regime = "GREEN"
        reasons = []
        
        if term_structure_status != "NORMAL":
            risk_regime = "RED"
            reasons.append(f"VIX Inversion ({vix_ratio:.2f})")
            
        if crash_status != "LOW":
            risk_regime = "RED"
            reasons.append(f"VVIX Spike ({vvix:.0f})")
            
        if breadth_status != "STABLE" and risk_regime != "RED":
            risk_regime = "YELLOW"
            reasons.append(f"Breadth Divergence ({rel_perf*100:.1f}%)")

        # Output State
        state = {
            "timestamp": datetime.datetime.now().isoformat(),
            "risk_regime": risk_regime,
            "reasons": reasons,
            "metrics": {
                "vix": vix,
                "vix3m": vix3m,
                "vix_ratio": round(vix_ratio, 3),
                "vvix": vvix,
                "spy_perf_10d": round(spy_perf*100, 2),
                "rsp_perf_10d": round(rsp_perf*100, 2),
                "rel_perf": round(rel_perf*100, 2)
            },
            "statuses": {
                "term_structure": term_structure_status,
                "breadth": breadth_status,
                "crash_risk": crash_status
            }
        }
        
        # Write to File
        with open(OUTPUT_FILE, "w") as f:
            json.dump(state, f, indent=2)
            
        print(f"✅ Health Check Complete. Regime: {risk_regime}")
        print(f"   Metrics: VIX Ratio={vix_ratio:.2f}, VVIX={vvix:.0f}, Breadth={rel_perf*100:.1f}%")
        
    except Exception as e:
        print(f"❌ Analysis Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Self-Test / Run Once
    analyze_health()
    
    # If running as a service, loop
    if len(sys.argv) > 1 and sys.argv[1] == "--loop":
        while True:
            time.sleep(900) # 15 Minutes
            analyze_health()
