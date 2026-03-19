import requests
import json
import time
import os
import sys
import re
from datetime import datetime, timezone

# --- CONFIGURATION ---
ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")
SOURCE_FILE = "active_portfolio.json"  # Read Position from here
OUTPUT_FILE = "nexus_greeks.json"     # Write Greeks to here

def parse_occ_symbol(symbol):
    """
    Parses an OCC Option Symbol (e.g., 'SPY 240116P00600000') to extract details.
    Returns: (Ticker, ExpiryDate, Type, Strike) or None if invalid.
    """
    try:
        clean_sym = symbol.replace(" ", "")
        # Relaxed Regex: Allow strike to be any length of digits
        match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d+)$", clean_sym)
        if not match:
            return None
            
        ticker = match.group(1)
        date_str = match.group(2) # YYMMDD
        opt_type = match.group(3) # C or P
        strike_str = match.group(4)
        
        expiry = datetime.strptime(date_str, "%y%m%d").strftime("%Y-%m-%d")
        
        # Handle Strike: If 8 digits, divide by 1000. If not, assume it's raw or needs logic.
        # Dashboard seems to send '710' for 710.0.
        # Standard OCC is 8 chars (00710000).
        if len(strike_str) == 8:
             strike = float(strike_str) / 1000.0
        else:
             # If short string (e.g. 710), it might be the strike directly?
             # Or 710 -> 710.0
             strike = float(strike_str)

        return ticker, expiry, opt_type, strike
    except Exception as e:
        print(f"⚠️ OCC Parse Error for {symbol}: {e}", flush=True)
        return None

def get_live_portfolio():
    """Reads the Dashboard's output to get ALL positions (Spreads & Singles)."""
    defaults = {"positions": [], "risk_profile": {}, "account_metrics": {}}
    
    if not os.path.exists(SOURCE_FILE): return defaults
        
    try:
        with open(SOURCE_FILE, 'r') as f:
            data = json.load(f)
            
        positions = []
        
        # 1. Handle Grouped Spreads (Legacy Format)
        if "grouped_positions" in data:
            for g in data["grouped_positions"]:
                qty = float(g.get("qty", 0))
                # Short Leg
                short_sym = g.get("short_leg")
                if short_sym:
                    parsed = parse_occ_symbol(short_sym)
                    if parsed:
                        t, d, typ, k = parsed
                        positions.append({"ticker": t, "qty": -qty, "type": "PUT" if typ=="P" else "CALL", "strike": k, "expiry": d, "raw": short_sym})
                
                # Long Leg
                long_sym = g.get("long_leg")
                if long_sym:
                    parsed = parse_occ_symbol(long_sym)
                    if parsed:
                        t, d, typ, k = parsed
                        positions.append({"ticker": t, "qty": qty, "type": "PUT" if typ=="P" else "CALL", "strike": k, "expiry": d, "raw": long_sym})

        # 2. Handle Ungrouped Directional Positions (Legacy Format)
        if "ungrouped_positions" in data:
            for p in data["ungrouped_positions"]:
                sym = p.get("ticker", "")
                parsed = parse_occ_symbol(sym)
                if parsed:
                    t, d, typ, k = parsed
                    # Determine type from OCC if possible, or fallback
                    # p['type'] might be "C" or "CALL"
                    raw_type = p.get("type", "C")
                    type_str = "CALL" if ("C" in raw_type or "CALL" in raw_type) else "PUT"
                    
                    positions.append({
                        "ticker": t, 
                        "qty": float(p.get("qty", 0)), 
                        "type": type_str, 
                        "strike": k, 
                        "expiry": d, 
                        "raw": sym
                    })
                    
        # 3. [FIX] Handle Raw TradeStation Positions (New Format)
        # If no grouped data, check for direct 'positions' list from TS
        if not positions and "positions" in data:
             raw_list = data["positions"]
             print(f"DEBUG: Found {len(raw_list)} raw positions.", flush=True)
             
             for p in raw_list:
                 sym = p.get("Symbol", "")
                 qty = float(p.get("Quantity", 0))
                 parsed = parse_occ_symbol(sym)
                 
                 if parsed:
                     print(f"DEBUG: Parsed OK: {sym}", flush=True)
                     t, d, typ, k = parsed
                     type_str = "PUT" if typ == "P" else "CALL"
                     positions.append({
                        "ticker": t, 
                        "qty": qty, 
                        "type": type_str, 
                        "strike": k, 
                        "expiry": d, 
                        "raw": sym
                    })
                 else:
                     print(f"DEBUG: Parse FAILED: {sym}", flush=True)

        return {
            "positions": positions,
            "risk_profile": data.get("risk_profile", {}),
            "account_metrics": data.get("account_metrics", {})
        }

        return {
            "positions": positions,
            "risk_profile": data.get("risk_profile", {}),
            "account_metrics": data.get("account_metrics", {})
        }
            
    except Exception as e:
        print(f"⚠️ Error reading portfolio source: {e}", flush=True)
        return defaults

# ... (fetch_greeks_uw remains unchanged) ...

import orats_connector

def fetch_greeks():
    # 1. Get Dynamic Portfolio
    port = get_live_portfolio()
    positions = port['positions']
    risk_profile = port['risk_profile']
    account_metrics = port['account_metrics']

    mkt_val = float(account_metrics.get("value_of_open_positions") or 0)

    if not positions:
        # [FIX] False-Empty Guard: If we have significant market value but 0 positions, it's a glitch.
        # [FIX] False-Empty Guard: If we have significant market value but 0 positions, it's a glitch.
        if mkt_val > 500:
            print(f"⚠️ SUSPICIOUS EMPTY PORTFOLIO (MktVal: ${mkt_val:.2f}). Raw Data Keys: {list(port.keys())}", flush=True)
            print(f"DEBUG: Positions Raw: {port.get('positions')}", flush=True)
            return

        print("⏳ No positions found. Writing Zero Greeks...", flush=True)
        # Write Zero Greeks to ensure dashboard updates
        zero_greeks = {
            "script": "nexus_greeks",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "greeks": {
                "delta": 0.0, "theta": 0.0, "vega": 0.0, "gamma": 0.0,
                "rent_cost_daily": 0.0, "iv_contract": 0
            },
            "api_usage": {"provider": "ORATS", "calls": 0},
            "active_trade": {}, "risk_profile": {}, "account_metrics": account_metrics
        }
        temp = f"{OUTPUT_FILE}.tmp"
        with open(temp, "w") as f: json.dump(zero_greeks, f)
        os.replace(temp, OUTPUT_FILE)
        return

    net_delta = 0.0
    net_gamma = 0.0
    net_theta = 0.0
    net_vega = 0.0

    print("-" * 60, flush=True)
    print(f"🔍 ANALYZING PORTFOLIO: {len(positions)} LEGS", flush=True)

    # --- OPTIMIZATION (ORATS): GROUP FETCHES BY TICKER ---
    # ORATS fetches the ENTIRE chain for a ticker, so we only need to fetch per ticker.
    required_tickers = set(p['ticker'] for p in positions)

    # Cache for the chains: Key = (Ticker, Expiry), Value = Dict of Contracts keyed by (Strike, Type)
    chain_cache = {}
    
    # Track usage simply by calls made
    api_hits = 0

    print(f"   ⚡ Optimizing: Fetching Chains for {len(required_tickers)} Tickers (ORATS)...", flush=True)

    for ticker in required_tickers:
        try:
            # Fetch FULL chain for ticker
            df = orats_connector.get_live_chain(ticker)
            api_hits += 1
            
            if df.empty:
                print(f"      ⚠️ No data for {ticker}", flush=True)
                continue
                
            # Group by expiry to match our cache structure: (Ticker, Expiry) -> { (Strike, Type): Row }
            # Ensure expiry format matches what positions use (YYYY-MM-DD)
            
            # Iterate rows is slow, but safe. 
            # Better: Group by expiry first.
            for expiry, group in df.groupby('expiry'):
                # expiry is a string "YYYY-MM-DD"
                cache_key = (ticker, expiry)
                if cache_key not in chain_cache:
                    chain_cache[cache_key] = {}
                
                # Build map for this expiry
                # We need to access row['strike'], row['type'], and greeks
                # Convert group to records for faster iteration
                records = group.to_dict('records')
                
                for row in records:
                    stk = float(row['strike'])
                    otype = row['type'].lower() # 'call' or 'put'
                    
                    # Store entire row as contract data
                    # ORATS Connector standardized keys: 'delta', 'gamma', 'theta', 'vega'
                    chain_cache[cache_key][(stk, otype)] = row
                    
        except Exception as e:
            print(f"      ❌ ORATS Fetch Error for {ticker}: {e}", flush=True)

    # ---------------------------------------------

    for p in positions:
        ticker = p['ticker']
        expiry = p['expiry']
        target_strike = float(p['strike'])
        target_type = "call" if p['type'].upper() == "CALL" else "put"

        contract = None

        # 1. Try Cache Lookup
        if (ticker, expiry) in chain_cache:
            contract_map = chain_cache[(ticker, expiry)]
            contract = contract_map.get((target_strike, target_type))

            # Fallback: Find closest strike
            if not contract:
                 compatible_keys = [k for k in contract_map.keys() if k[1] == target_type]
                 if compatible_keys:
                     closest_key = min(compatible_keys, key=lambda k: abs(k[0] - target_strike))
                     if abs(closest_key[0] - target_strike) < 0.5:
                         contract = contract_map[closest_key]

        if contract:
            qty = p['qty']
            multiplier = 100 * qty

            # ORATS Connector provides generic 'delta', 'gamma' etc. correct for the type
            r_delta = float(contract.get('delta', 0))
            r_gamma = float(contract.get('gamma', 0))
            r_theta = float(contract.get('theta', 0))
            r_vega = float(contract.get('vega', 0))

            # Position Impact
            p_delta = r_delta * multiplier
            p_gamma = r_gamma * multiplier
            p_theta = r_theta * multiplier
            p_vega = r_vega * multiplier

            net_delta += p_delta
            net_gamma += p_gamma
            net_theta += p_theta
            net_vega += p_vega

            print(f"   ► {qty}x {p['raw']} (Δ {r_delta:.3f} | Γ {r_gamma:.4f}) -> Net Δ {p_delta:.1f} | Γ {p_gamma:.1f}", flush=True)

        else:
            print(f"   ❌ Failed to find data for: {p['raw']}", flush=True)

    print(f"💰 PORTFOLIO NET: Δ {net_delta:.1f} | Γ {net_gamma:.1f} | Θ {net_theta:.1f}", flush=True)
    print(f"📊 API USAGE: {api_hits} Fetches (ORATS)", flush=True)
    print("-" * 60, flush=True)

    # Dump separate Greeks file
    output = {
        "script": "nexus_greeks",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "greeks": {
            "delta": net_delta,
            "theta": net_theta,
            "vega": net_vega,
            "gamma": net_gamma,
            "rent_cost_daily": net_theta,
            "iv_contract": 0 
        },
        "api_usage": {"provider": "ORATS", "calls": api_hits},
        "active_trade": {}, 
        "risk_profile": risk_profile,
        "account_metrics": account_metrics
    }

    temp = f"{OUTPUT_FILE}.tmp"
    with open(temp, "w") as f: json.dump(output, f)
    os.replace(temp, OUTPUT_FILE)


# --- MARKET HOURS LOGIC ---
def is_market_hours():
    """
    Checks if market is open (including reasonable pre/post buffer).
    Core: 9:30 - 16:00 ET.
    Extended Buffer for Greeks: 9:00 - 16:30 ET.
    """
    try:
         # EST/EDT
         now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=-5)))
         if now.weekday() >= 5: return False # Sat/Sun
         
         # 9:00 AM to 4:30 PM ET
         start = now.replace(hour=9, minute=0, second=0, microsecond=0)
         end = now.replace(hour=16, minute=30, second=0, microsecond=0)
         
         return start <= now <= end
    except: return True # Default to True if timezone fails

print("🔵 NEXUS DYNAMIC GREEKS (V4 - ORATS POWERED) STARTED", flush=True)
TRIGGER_FILE = "nexus_greeks.trigger"

# 3. Dynamic Loop
while True:
    # Determine Mode
    market_open = is_market_hours()
    manual_trigger = os.path.exists(TRIGGER_FILE)
    
    # CLEAR TRIGGER
    if manual_trigger:
        try: os.remove(TRIGGER_FILE)
        except: pass
        print("⚡ Manual Refresh Triggered!", flush=True)

    # DECIDE: Run or Sleep?
    # Run if: Market Open OR Manual Trigger OR First Run (implied by just starting)
    # Actually, we just run fetch_greeks() then sleep based on mode.
    
    try:
        if market_open or manual_trigger:
            fetch_greeks()
        else:
            # IN ECO MODE: We might want to run ONCE every hour?
            # Or just skip?
            # Let's run sparingly (every 15 mins) to keep system alive but save data
            # No, if closed, data doesn't change. 
            # But user might have 'greeks.trigger' to force update.
            print("💤 Market Closed (ECO MODE). Sleeping...", flush=True)
            pass 
    except Exception as e:
        print(f"❌ Greeks Loop Crash: {e}", flush=True)
        time.sleep(10)

    # SLEEP LOGIC
    # Active: 60s (Reduced from 30s to save API)
    # Closed: 300s (Check for manual trigger every 1s, but loop duration)
    
    sleep_target = 60 if market_open else 300
    
    # [CRITICAL FIX] MANDATORY COOLDOWN to protect API LIMIT
    # We must sleep at least 60s BEFORE checking triggers to prevent crash-loops or trigger-spam from draining API.
    # 15,000 req / day = ~625 req / hour. 
    # One cycle = 2-3 reqs. So 60s sleep = ~120-180 req / hour (Safe).
    
    print(f"⏳ Cooling down for {sleep_target}s...", flush=True)
    
    # 1. Mandatory Sleep (Uninterruptible)
    SAFE_SLEEP = 60
    time.sleep(SAFE_SLEEP)
    
    # 2. Remaining Sleep (Interruptible by Trigger - checks remaining time)
    remaining = sleep_target - SAFE_SLEEP
    if remaining > 0:
        for _ in range(remaining):
            if os.path.exists(TRIGGER_FILE):
                break # Break sleep to loop and handle trigger

