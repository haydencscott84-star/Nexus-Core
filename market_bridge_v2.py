import json
import os
import time
import datetime
import uuid

# --- CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)).replace("haydencscott", "haydenscott")

# INPUT SOURCES (Map: Logical Name -> Filename)
INPUT_SOURCES = {
    "spy_profile": "nexus_spy_profile.json",
    "spx_profile": "nexus_spx_profile.json", # [FIX] Point to correct output from spx_profiler_nexus.py
    "sweeps_v1": "nexus_sweeps_v1.json",
    "sweeps_v2": "nexus_sweeps_v2.json",
    "tape": "nexus_tape.json",
    "history": "nexus_history.json",
    "portfolio_greeks": "nexus_greeks.json",
    "structure": "nexus_structure.json",
    "portfolio": "nexus_portfolio.json",
    "spy_flow": "nexus_spy_flow_details.json", # [FIX] Updated to V2 filename
    "spy_levels": "market_levels.json", # [NEW] Converted SPY Levels from SPX Profiler
    "hedge_state": "hedge_state.json", # [NEW] Futures Hedge Data
    "quant_data": "nexus_quant.json" # [NEW] Quant Logic
}

# FALLBACKS
FALLBACK_SOURCES = {
    "spy_profile": "nexus_dash_metrics.json"
}

OUTPUT_FILE = os.path.join(SCRIPT_DIR, "market_state.json")

class BridgeEngine:
    def __init__(self):
        self.memory = {} # Stores last valid data for each source
        self.consecutive_failures = {k: 0 for k in INPUT_SOURCES}
        self.consecutive_failures = {k: 0 for k in INPUT_SOURCES}
        self.log_file = "bridge_status.log"
        self.persistence_file = os.path.join(SCRIPT_DIR, "bridge_persistence.json")
        self.cycles = 0
        self.load_persistence()

    def load_persistence(self):
        try:
            if os.path.exists(self.persistence_file):
                with open(self.persistence_file, 'r') as f:
                    self.memory = json.load(f)
                self.log_status(f"Loaded Persistence: {list(self.memory.keys())}")
        except Exception as e:
            self.log_status(f"Persistence Load Error: {e}")

    def save_persistence(self):
        try:
            # Atomic Write
            tmp = f"{self.persistence_file}.tmp"
            with open(tmp, 'w') as f:
                json.dump(self.memory, f, indent=2)
            os.replace(tmp, self.persistence_file)
        except Exception as e:
            print(f"Persistence Save Error: {e}")

    def fetch_live_price(self, ticker="SPY"):
        """Direct fetch from YFinance if local feeds are stale."""
        try:
            import yfinance as yf
            # Use fast info or history
            t = yf.Ticker(ticker)
            # Try fast_info first (faster)
            price = t.fast_info.last_price
            if price: return float(price)
            
            # Fallback to history
            hist = t.history(period="1d")
            if not hist.empty: return float(hist['Close'].iloc[-1])
            return 0.0
        except Exception as e:
            self.log_status(f"Live Price Fetch Error: {e}")
            return 0.0

    def log_status(self, message):
        try:
            with open(self.log_file, "a") as f:
                f.write(f"[{datetime.datetime.now().isoformat()}] {message}\n")
        except: pass

    def safe_read_json(self, filename):
        filepath = os.path.join(SCRIPT_DIR, filename)
        if not os.path.exists(filepath):
            return None, 999999, False # Return None to signal failure
        
        # [ROBUST] Retry Loop for Atomic Reads
        max_retries = 3
        for attempt in range(max_retries):
            try:
                mtime = os.path.getmtime(filepath)
                age = time.time() - mtime
                with open(filepath, "r") as f:
                    content = f.read().strip()
                
                if not content: 
                    # If empty, might be mid-write. Sleep and retry.
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    return None, age, False
                
                try:
                    data = json.loads(content)
                    # Basic validation: Must be dict
                    if not isinstance(data, dict): return None, age, False
                    return data, age, True
                except json.JSONDecodeError:
                    if attempt < max_retries - 1:
                        time.sleep(0.1)
                        continue
                    pass # Fall through to error
                    
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(0.1)
                    continue
                pass
        
        return None, 999999, False


    def format_gex(self, value):
        try:
            val = float(value)
        except (ValueError, TypeError):
            return "N/A"
        abs_val = abs(val)
        s = f"{abs_val/1e9:.1f}B" if abs_val >= 1e9 else (f"{abs_val/1e6:.1f}M" if abs_val >= 1e6 else f"{abs_val:.0f}")
        return f"-{s} (Bearish)" if val < 0 else f"+{s} (Bullish)"

    def format_momentum(self, score):
        try: s = float(score)
        except: return "NEUTRAL"
        return "STRONG_BUY_SIDE" if s > 5 else ("STRONG_SELL_SIDE" if s < -5 else "NEUTRAL")

    def get_data(self, source_name, filename):
        """Smart Fetch: Returns (data, status_dict)"""
        data, age, success = self.safe_read_json(filename)
        
        # Fallback Logic
        if not success and source_name == "spy_profile":
            fb_file = FALLBACK_SOURCES.get("spy_profile")
            if fb_file:
                fb_data, fb_age, fb_success = self.safe_read_json(fb_file)
                if fb_success:
                    self.log_status(f"Using Fallback {fb_file} for {source_name}")
                    data = fb_data
                    age = fb_age
                    success = True
                    data['is_fallback'] = True

        # Persistence Logic
        if success:
            self.memory[source_name] = data
            self.consecutive_failures[source_name] = 0
            
            # [SAFETY] Semantic Validation for Critical Feeds
            is_valid = True
            if source_name == "spx_profile":
                # Check for Zero GEX (Corrupt Calc)
                try:
                    net_gex = float(data.get("net_gex", 0))
                    gex_struct = data.get("gex_structure", [])
                    if net_gex == 0 and not gex_struct and "is_fallback" not in data:
                        is_valid = False
                        error_msg = "Semantic Error: Zero GEX"
                except: pass
            
            if is_valid:
                # Update Memory only if Semantically Valid
                self.memory[source_name] = data
                self.save_persistence() # Persist good data
                status = "ONLINE"
            else:
                # Treat as Failure if Semantically Invalid
                success = False
                self.consecutive_failures[source_name] += 1
                if source_name in self.memory:
                    data = self.memory[source_name]
                    status = "STALE (SEMANTIC FAIL)"
                else:
                    status = "OFFLINE (SEMANTIC FAIL)"
            
            if age > 600: status = "STALE"
            if success and is_valid: error_msg = f"Last update {int(age)}s ago" if status == "STALE" else "None"
        else:
            self.consecutive_failures[source_name] += 1
            # Use Memory if available
            if source_name in self.memory:
                data = self.memory[source_name]
                status = "PERSISTED" # New Status: Data is old but kept alive
                age = 999 # Unknown real age of memory, or track it?
                error_msg = f"Read Failed. Using Last Known Good State."
            else:
                data = {}
                status = "OFFLINE"
                error_msg = "File not found & No History"
        
        # [HARDENING] Don't crash on invalid age formatting
        try:
            readable_update = datetime.datetime.fromtimestamp(time.time() - age).strftime('%H:%M:%S') if age < 999999 else "N/A"
        except:
            readable_update = "N/A"

        feed_status = {
            "status": status,
            "error": error_msg,
            "age": int(age) if age < 999999 else 999999,
            "last_update": readable_update
        }
        return data, feed_status

    def run_cycle(self):
        raw_data = {}
        feed_health = {}
        
        # [DEBUG] Log Sources ONCE on startup
        if self.cycles == 0:
            self.log_status(f"DEBUG: Active Sources: {list(INPUT_SOURCES.keys())}")
            
        self.cycles += 1

        
        # 1. Ingest
        for name, filename in INPUT_SOURCES.items():
            d, s = self.get_data(name, filename)
            raw_data[name] = d
            feed_health[name] = s

        # 2. System Health
        critical_feeds = ["spy_profile", "spx_profile", "portfolio"]
        offline = sum(1 for k in critical_feeds if feed_health[k]['status'] == "OFFLINE")
        persisted = sum(1 for k in critical_feeds if feed_health[k]['status'] == "PERSISTED")
        
        if offline > 0: global_status = "DEGRADED" # Was CRITICAL, but let's say DEGRADED if partial
        elif persisted > 0: global_status = "WARNING"
        else: global_status = "OPERATIONAL"

        # 3. Merge
        spy = raw_data["spy_profile"]
        spx = raw_data["spx_profile"]
        tape = raw_data["tape"]
        history = raw_data["history"]
        struct = raw_data["structure"]
        port = raw_data["portfolio"]
        port_greeks = raw_data["portfolio_greeks"]
        spy_flow = raw_data["spy_flow"]
        spy_flow = raw_data["spy_flow"]
        spy_levels = raw_data["spy_levels"] # [NEW]
        hedge_data = raw_data["hedge_state"] # [NEW]
        quant_data = raw_data["quant_data"] # [NEW]
        
        # Merge Portfolio & Hedge
        active_pos_merged = port.copy() if port else {}
        
        # Ensure 'greeks' exists
        if "greeks" not in active_pos_merged: 
            active_pos_merged["greeks"] = {"delta": 0, "gamma": 0, "theta": 0, "vega": 0, "net_delta": 0}

        if port_greeks:
            greeks = port_greeks.get("greeks", port_greeks) # Handle nested or flat
            active_pos_merged["greeks"].update(greeks)
            
        # [PATCH] Recalculate Percentages if missing (Fix for Zero Exposure Display)
        acc = active_pos_merged.get("account_metrics", {})
        try:
            equity = float(acc.get("equity", 0))
            if equity > 0:
                if acc.get("exposure_pct", 0) == 0:
                    acc["exposure_pct"] = (float(acc.get("exposure", 0)) / equity) * 100
                if acc.get("pnl_pct", 0) == 0:
                    acc["pnl_pct"] = (float(acc.get("unrealized_pnl", 0)) / equity) * 100
                active_pos_merged["account_metrics"] = acc
        except: pass

        # [NEW] Merge Hedge Delta
        if not hedge_data:
            # [ROBUSTNESS] Double Check Hedge State because it is Critical
            try:
                # Debug path check removed for production
                with open(os.path.join(SCRIPT_DIR, "hedge_state.json"), "r") as f:
                    hd_check = json.load(f)
                    # Relaxed check: Just valid dict is enough to pass, we filter 0 qty later if needed
                    if hd_check and isinstance(hd_check, dict):
                        self.log_status(f"WARN: Recovered Hedge State from Double-Check: {hd_check}")
                        hedge_data = hd_check
            except Exception as e:
                 pass # Squelch error for production logs

        if hedge_data:
            # Safe Float Conversion
            try: h_delta = float(hedge_data.get("hedged_delta", 0))
            except: h_delta = 0.0
            
            curr_delta = float(active_pos_merged["greeks"].get("delta", 0))
            
            # Calculate Net Delta
            active_pos_merged["greeks"]["net_delta"] = curr_delta + h_delta
            active_pos_merged["greeks"]["hedge_delta"] = h_delta
            
            # Inject Hedge Context for Auditor
            active_pos_merged["hedge_data"] = hedge_data
            
            # [FIX] Ensure Ticker is not N/A if we have a hedge but no options
            if active_pos_merged.get("ticker", "N/A") == "N/A":
                 active_pos_merged["ticker"] = "HEDGED_PORTFOLIO"
                 active_pos_merged["type"] = "HEDGE"
            
        # Merge Sweeps
        s1 = raw_data["sweeps_v1"]
        s2 = raw_data["sweeps_v2"]
        active_sweeps = s2 if feed_health["sweeps_v2"]["status"] == "ONLINE" else s1

        master_record = {
            "timestamp": datetime.datetime.now().isoformat(),
            "global_system_status": global_status,
            "data_quality": feed_health,
            "historical_context": {
                **history.get("trend_signals", {}),
                "levels": history.get("persistent_levels", {})
            },
            "market_structure": {
                "SPY": {
                    "price": self.fetch_live_price("SPY") if (feed_health["spy_profile"]["status"] != "ONLINE" or spy.get("current_price", 0) == 0) else spy.get("current_price", 0),
                    "net_gex": self.format_gex(spy.get("net_gex", 0)),
                    # [PATCHED] Prioritize Converted Levels from SPX Profiler
                    # [FIX] Remap keys to match viewer_dash_nexus.py JSON output
                    "call_wall": spy.get("call_wall", 0), 
                    "put_wall": spy.get("put_wall", 0),
                    "zero_gamma": spy.get("gamma_flip_strike") or spy.get("zero_gamma", 0),
                    "vol_trigger": spy_levels.get("vol_trigger") if spy_levels else 0, # [NEW]
                    "deep_flow": spy_flow.get("flow_sentiment", {}),
                    "divergence": spy_flow.get("divergence_signals", {}),
                    "trend_metrics": struct.get("SPY", {}).get("trend_metrics", {}) # [NEW] RVOL/Hourly RVOL
                },
                "SPX": {
                    "price": spx.get("spx_price", 0) or spx.get("spot", 0),
                    "net_gex": self.format_gex(spx.get("net_gex", 0) or spx.get("total_gamma", 0)),
                    
                    # [FIX] Map new SPX Profiler keys for Sheets/Auditor
                    "call_wall": spx.get("short_gamma_wall_above") or spx.get("call_wall", 0),
                    "put_wall": spx.get("short_gamma_wall_below") or spx.get("put_wall", 0),
                    "magnet": spx.get("volume_poc_strike") or spx.get("magnet", 0),
                    "zero_gamma": spx.get("gex_flip_point") or spx.get("zero_gamma_level", 0),
                    
                    "levels": spx.get("major_levels", {}),
                    "flow_breakdown": spx.get("flow_stats", {}),
                    "trajectory": spx.get("trajectory", "Analyzing..."), # [NEW]
                    "trend_metrics": struct.get("SPX", {}).get("trend_metrics", {}) # [NEW] Includes RVOL
                },
                # "trend": struct.get("trend_status", {}) # Legacy/Removed
            },
            "flow_sentiment": {
                "sweeps": {
                    "total_premium": active_sweeps.get("total_premium", 0),
                    "sentiment_scores": active_sweeps.get("sentiment_scores", {"SPY": 0, "SPX": 0}),
                    "top_bullish": active_sweeps.get("bullish_flow_list", [])[:5],
                    "top_bearish": active_sweeps.get("bearish_flow_list", [])[:5]
                },
                "tape": {
                    "momentum_label": self.format_momentum(tape.get("tape_momentum_score", 0)),
                    "momentum_score": tape.get("tape_momentum_score", 0)
                }
            },
            "active_position": active_pos_merged,
            "quant_analysis": quant_data.get("analysis", {}) if quant_data else {}
        }

        # 4. Write
        # [ATOMIC WRITE] Use a unique temporary file then rename
        tmp_file = f"{OUTPUT_FILE}.tmp.{uuid.uuid4()}"
        
        try:
            with open(tmp_file, "w") as f:
                json.dump(master_record, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
                
            # Atomic Replace
            os.replace(tmp_file, OUTPUT_FILE)
            # self.log_status(f"Updated {OUTPUT_FILE}") # Too verbose for rapid updates
            
        except Exception as e:
            self.log_status(f"Write Error: {e}")
            # Clean up tmp file if write failed
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except:
                    pass

def main():
    print("Starting Indestructible Bridge (v2 Persistence)...")
    engine = BridgeEngine()
    engine.log_status("=== BRIDGE STARTED ===")
    while True:
        try:
            engine.run_cycle()
        except Exception as e:
            print(f"CRITICAL BRIDGE FAILURE: {e}")
            engine.log_status(f"CRITICAL FAILURE: {e}")
        time.sleep(5)

if __name__ == "__main__":
    main()
