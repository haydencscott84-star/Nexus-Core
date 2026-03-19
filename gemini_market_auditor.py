import nexus_lock
nexus_lock.enforce_singleton()
import google.generativeai as genai
import os
import time
import datetime
import requests
import json
import pytz # Added for Timezone Support

# --- CONFIGURATION ---
# 1. Get your API Key here: https://aistudio.google.com/app/apikey
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.5-flash' 
MAX_DATA_AGE = 3600 # 1 Hour
MARKET_STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_state.json")
SWEEPS_V2_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_sweeps_v2.json")
SPY_FLOW_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_spy_flow_details.json")
THESIS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spy_thesis.json")
STRUCTURE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_structure.json")
RISK_PROFILES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk_profiles.json")
from nexus_config import DISCORD_WEBHOOK_URL

# --- SETUP GEMINI ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

def safe_read_json(filepath):
    if not os.path.exists(filepath):
        print(f"⚠️ File not found: {filepath}")
        return {}
    try:
        with open(filepath, "r") as f: return json.load(f)
    except Exception as e:
        print(f"❌ JSON Read Error ({filepath}): {e}")
        return {}

import zmq
from nexus_config import ZMQ_PORT_NOTIFICATIONS

# --- ZMQ SETUP ---
ctx_audit = zmq.Context()
sock_audit = ctx_audit.socket(zmq.PUSH)
sock_audit.connect(f"tcp://localhost:{ZMQ_PORT_NOTIFICATIONS}")

def send_discord_msg(text, color=None, message_id=None, fields=None):
    """
    [REFACTORED] Sends market analysis via ZMQ to Notification Service.
    Uses 'topic'='GEMINI_AUDITOR' to enable persistent message editing.
    """
    try:
        color_val = color if color else 3447003 # Default Blue
        
        payload = {
            "title": "🧠 Gemini Market Auditor",
            "message": text[:4000], # [FIX] Truncate to safe limit
            "color": color_val,
            "fields": fields[:24] if fields else [], # [FIX] Cap at 24 fields
            # [FIX] Only send topic if we intend to edit. Otherwise, send None to force fresh message.
            "topic": "GEMINI_AUDITOR" if message_id else None
        }
        
        sock_audit.send_json(payload, flags=zmq.NOBLOCK)
        print("✅ Analysis pushed to Notification Service (ZMQ)")
        return "ZMQ_HANDLED" # Return dummy ID so logic doesn't break
        
    except Exception as e:
        print(f"❌ ZMQ Push Failed: {e}")
        return None



# ... (Wait, I should use replace_file_content to rewrite the whole script or a large chunk)
# Let's rewrite the 'analyze_market_context' and 'main' to be cleaner.

class MarketAuditor:
    def __init__(self):
        self.last_sent_msg = None
        self.last_message_id = None # Track the ID for editing

    def run_cycle(self):
        print(f"📉 Reading Market State from {MARKET_STATE_FILE}...")
        state = safe_read_json(MARKET_STATE_FILE)
        
        # [NEW] Helper for Currency Formatting (Moved here for scope availability)
        def fmt_money(val):
            if not isinstance(val, (int, float)): return str(val)
            abs_val = abs(val)
            if abs_val >= 1_000_000_000:
                return f"${val/1_000_000_000:.2f}B"
            elif abs_val >= 1_000_000:
                return f"${val/1_000_000:.2f}M"
            elif abs_val >= 1_000:
                return f"${val/1_000:.2f}K"
            else:
                return f"${val:.2f}"

        # [NEW] Direct Data Injection
        SWEEPS_V2_FILE = globals().get('SWEEPS_V2_FILE', os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_sweeps_v2.json"))
        SWEEPS_V1_FILE = globals().get('SWEEPS_V1_FILE', os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_sweeps_v1.json"))
        SPY_FLOW_FILE = globals().get('SPY_FLOW_FILE', os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_spy_flow_details.json"))
        
        sweeps_v2_data = safe_read_json(SWEEPS_V2_FILE)
        sweeps_v1_data = safe_read_json(SWEEPS_V1_FILE)
        spy_flow_data = safe_read_json(SPY_FLOW_FILE)
        
        # [NEW] SPX Structure Injection (The Fix)
        gex_framework = "No GEX Data Available"
        try:
            spx_prof_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_spx_profile.json")
            spx_prof_data = safe_read_json(spx_prof_path)
            gex_struct = spx_prof_data.get('gex_structure', [])
            
            rows = []
            if gex_struct and len(gex_struct) > 0:
                # Get Basis for Conversion (Dynamic)
                basis = 0
                try:
                    mkt_s = state.get('market_structure', {})
                    spx_now = mkt_s.get('SPX', {}).get('price', 0)
                    spy_now = mkt_s.get('SPY', {}).get('price', 0)
                    if spx_now > 0 and spy_now > 0:
                        basis = spx_now - (spy_now * 10)
                except: basis = 0

                def fmt_g(val): 
                    if not val: return "N/A"
                    v = float(val)
                    if abs(v) >= 1e9: return f"${v/1e9:.1f}B"
                    if abs(v) >= 1e6: return f"${v/1e6:.1f}M"
                    return f"${v:.0f}"
                
                def fmt_s(val):
                    if not val: return "N/A"
                    v = float(val)
                    # Use Basis if reasonable, else /10 approximation
                    if basis != 0 and abs(basis) < 500: # Sanity check basis
                         spy_equiv = (v - basis) / 10
                    else:
                         spy_equiv = v / 10
                    return f"{v:.0f} (${spy_equiv:.2f})"

                r0 = gex_struct[0]
                # [NEW] P/C Ratio Injection
                pc_vol = spx_prof_data.get('gex_metrics', {}).get('pc_ratio_volume', 0.0)
                pc_oi = spx_prof_data.get('gex_metrics', {}).get('pc_ratio_oi', 0.0)
                
                # [RESTORED] Flip & Pin Data
                flip = fmt_s(r0.get('gex_flip_point'))
                pin = fmt_s(r0.get('volume_poc_strike'))
                pain = fmt_s(r0.get('max_pain_strike'))
                gex_tot = fmt_g(r0.get('total_gamma'))

                rows.append(f"   * 0DTE: Total GEX: {gex_tot} | Flip: {flip} | Pin (POC): {pin} | Pain: {pain}")
                rows.append(f"   * [HEDGE METRICS] P/C Vol: {pc_vol:.2f} | P/C OI: {pc_oi:.2f} (Context: >1.0 = Put Heavy, <0.7 = Call Heavy)")
                
                # [NEW] Next Friday Logic
                def get_next_friday():
                    today = datetime.datetime.now().date()
                    # If Today is Mon(0)-Thu(3), target is This Friday(4)
                    # If Today is Fri(4)-Sun(6), target is Next Friday
                    if today.weekday() < 4:
                        days_ahead = 4 - today.weekday()
                    else:
                        days_ahead = (7 - today.weekday()) + 4 # Days to next week + 4 (Fri)
                        
                    target = today + datetime.timedelta(days=days_ahead)
                    return target.strftime('%Y-%m-%d')

                target_friday_str = get_next_friday()
                
                # Find the row matching next friday
                r1 = None
                r1_label = "NEXT"
                
                # Search skipping the first one (0DTE)
                for item in gex_struct[1:]:
                    if item.get('date') == target_friday_str:
                        r1 = item
                        r1_label = f"NEXT (Friday {target_friday_str[5:]})"
                        break
                
                # Fallback to index 1 if not found
                if not r1 and len(gex_struct) > 1:
                    r1 = gex_struct[1]
                    r1_label = f"NEXT ({r1.get('date', 'Unknown')[5:]})"

                if r1:
                    f1 = fmt_s(r1.get('gex_flip_point'))
                    p1 = fmt_s(r1.get('volume_poc_strike'))
                    pn1 = fmt_s(r1.get('max_pain_strike'))
                    g1 = fmt_g(r1.get('total_gamma'))
                    rows.append(f"   * {r1_label}: Total GEX: {g1} | Flip: {f1} | Pin: {p1} | Pain: {pn1}")
                    
                    # [NEW] Next Expiry Hedge Metrics (SPX)
                    pc_vol_next = r1.get('pc_ratio_volume')
                    pc_oi_next = r1.get('pc_ratio_oi')
                    
                    if pc_vol_next is not None and pc_oi_next is not None:
                         rows.append(f"   * [HEDGE METRICS] P/C Vol: {pc_vol_next:.2f} | P/C OI: {pc_oi_next:.2f}")
            
            if rows: gex_framework = "\n".join(rows)
        except Exception as e:
            print(f"GEX Framework Error: {e}")

        # [FIXED] Pure Money Flow Calculation (Net Premium)
        # We process the raw lists from V3 to ensure we get Money Flow ($), not Delta.
        
        net_flow_0dte = 0.0
        net_flow_next = 0.0
        
        # Helper to process lists
        def process_flow_list(flow_list, sign=1):
            d0 = 0.0; d1 = 0.0
            today_ts = datetime.datetime.now().date()
            
            for flow in flow_list:
                # [SAFETY] Ensure flow is from TODAY
                ts = flow.get('executed_at', 0)
                try:
                    fd = datetime.datetime.fromtimestamp(ts).date()
                    if fd != today_ts: continue
                except: continue
                
                dte = flow.get('parsed_dte', 0)
                prem = float(flow.get('total_premium', 0))
                
                # [NEW] Aggressor Weighting (Match TUI Logic)
                price = flow.get('price', 0)
                bid = flow.get('bid', 0)
                ask = flow.get('ask', 0)
                weight = 0.5 # Default Neutral
                
                if bid > 0 and ask > 0:
                    if price >= ask: weight = 1.0 # Aggressive
                    elif price <= bid: weight = 0.1 # Passive
                else:
                    # Fallback to Sentiment
                    sent = flow.get('sentiment_str', 'MID')
                    if sent == 'BUY': weight = 1.0
                    elif sent == 'SELL': weight = 0.1
                
                weighted_prem = prem * weight
                
                if dte <= 3: d0 += weighted_prem
                else: d1 += weighted_prem
            return d0 * sign, d1 * sign

        b0, b1 = process_flow_list(sweeps_v2_data.get('bullish_flow_list', []), 1)
        s0, s1 = process_flow_list(sweeps_v2_data.get('bearish_flow_list', []), -1)
        
        net_flow_0dte = b0 + s0
        net_flow_next = b1 + s1
        
        # [METRICS] Separate Delta Metrics (Do not mix with Money Flow)
        sw_metrics = sweeps_v2_data.get('metrics', {})
        delta_exposure_total = sw_metrics.get('3dte_plus_net_delta', 0) + sw_metrics.get('0dte_net_delta', 0)
        
        print(f"💰 MONEY FLOW: 0DTE=${net_flow_0dte:,.0f} | 3DTE+=${net_flow_next:,.0f}")
        print(f"📐 DELTA EXP: {delta_exposure_total:,.0f}")

        # [REMOVED] Sweeps V1 Data (Deprecated/Stale)
        spy_0dte_val = spy_flow_data.get('flow_sentiment', {}).get('0dte_flow', 0)
        # Map 'next_expiry_bias' to Total/Structure Flow
        spy_prof_delta = spy_flow_data.get('flow_sentiment', {}).get('next_expiry_bias', 0)

        if not state:
            print("❌ Market State is empty or missing.")
            return

        # --- CIRCUIT BREAKER (HEARTBEAT CHECK) ---
        system_status = state.get("global_system_status", "UNSAFE")
        feed_health = state.get("feed_health", {})
        
        # NEW: Handle DEGRADED gracefully
        if system_status == "CRITICAL_OFFLINE":
             error_msg = f"**⛔ SYSTEM HALT: ALL FEEDS OFFLINE**\nCheck VPS immediately."
             print(f"⛔ CIRCUIT BREAKER: {error_msg}")
             self.send_alert(error_msg, color=15158332) # RED
             return
        
        elif system_status == "DEGRADED":
            # Warn but PROCEED
            offline_feeds = [k for k,v in feed_health.items() if v.get('status') == 'OFFLINE']
            warn_msg = f"**⚠️ SYSTEM DEGRADED**\nOffline: {', '.join(offline_feeds)}\n*Proceeding with partial analysis...*"
            print(f"⚠️ {warn_msg}")
            # We do NOT return here. We proceed.

        # --- EXTRACT DATA (Safely) ---
        mkt = state.get('market_structure', {})
        spy = mkt.get('SPY', {})
        spx = mkt.get('SPX', {})
        flow = state.get('flow_sentiment', {})
        
        # Handle Missing Data in Prompt
        spy_price = spy.get('price', 'UNKNOWN')
        spy_gex = spy.get('net_gex', 'UNKNOWN')
        spx_gex = spx.get('net_gex', 'UNKNOWN')
        tape_mom = flow.get('tape', {}).get('momentum_label', 'UNKNOWN')
        
        # --- HISTORICAL CONTEXT (LONG-TERM MEMORY) ---
        history = state.get("historical_context", {})
        hist_trend = history.get("flow_direction", "UNKNOWN")
        hist_score = history.get("sentiment_score_5d", "N/A")
        hist_oi = history.get("oi_trend", "N/A")
        
        # NEW: Snapshot Header Logic
        hist_traj = history.get("trajectory", "N/A")
        hist_div = history.get("divergence", "NONE")
        hist_pain = history.get("flow_pain", 0)
        hist_levels = history.get("levels", {})
        major_sup = hist_levels.get("major_support", "N/A")
        major_res = hist_levels.get("major_resistance", "N/A")
        
        # [NEW] Helper for Price Formatting
        def fmt_price(val):
            try:
                if isinstance(val, (int, float)): return f"{val:.2f}"
                return f"{float(val):.2f}"
            except: return str(val)

        # --- TECHNICALS EXTRACTION (NEW) ---
        trend = spy.get('trend_metrics', {})
        sma_20 = fmt_price(trend.get('sma_20', 'N/A'))
        sma_50 = fmt_price(trend.get('sma_50', 'N/A'))
        sma_200 = fmt_price(trend.get('sma_200', 'N/A'))
        vwap = fmt_price(trend.get('vwap', spy_price))
        stack_status = trend.get('stack_status', 'UNKNOWN')
        stack_status = trend.get('stack_status', 'UNKNOWN')
        extension = trend.get('extension_status', 'NORMAL')
        rvol = trend.get('rvol', 0)
        h_rvol = trend.get('hourly_rvol', 0)
        
        # SPX Trend
        spx_trend = spx.get('trend_metrics', {})
        spx_rvol = spx_trend.get('rvol', 0)
        spx_h_rvol = spx_trend.get('hourly_rvol', 0)
        
        # Format current price too
        spy_price = fmt_price(spy_price)
        
        # [FIX] Read RVOL directly from nexus_structure.json (Removing Bridge Latency)
        # This aligns the Auditor exactly with nexus_sheets_bridge.py
        NEXUS_STRUCTURE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_structure.json")
        try:
             structure_direct = safe_read_json(NEXUS_STRUCTURE_FILE)
             
             # SPY RVOL
             struct_spy = structure_direct.get("SPY", {})
             rvol = struct_spy.get("trend_metrics", {}).get("rvol", 0)
             h_rvol = struct_spy.get("trend_metrics", {}).get("hourly_rvol", 0)
             # Force Index
             fi_13 = struct_spy.get("trend_metrics", {}).get("force_index_13", 0)
             trend_str = struct_spy.get("trend_metrics", {}).get("trend_strength", 50)
             
             # SPX RVOL
             struct_spx = structure_direct.get("SPX", {})
             spx_rvol = struct_spx.get("trend_metrics", {}).get("rvol", 0)
             spx_h_rvol = struct_spx.get("trend_metrics", {}).get("hourly_rvol", 0)
             
             print(f"DEBUG RVOL (Direct): SPY={rvol} SPX={spx_rvol}")
        except Exception as e:
             print(f"RVOL Direct Read Error: {e}")
             # Fallback (keep existing values from state if needed, but they are already set above)

        active_pos = state.get("active_position", {})
        greeks = active_pos.get("greeks", {}) # Merged by Bridge
        
        # [UPDATED] READ HEDGE STATE FROM BRIDGE (Unified)
        hedge_data = active_pos.get("hedge_data", {})
        hedge_context = ""
        
        if hedge_data and hedge_data.get("qty", 0) != 0:
            h_qty = hedge_data.get("qty")
            h_sym = hedge_data.get("symbol")
            h_delta = hedge_data.get("hedged_delta", 0)
            h_pnl = hedge_data.get("pnl", 0)
            
            # [ESTIMATE] Hedge P/L % (Assume $1200 Margin per Contract for MESH)
            # This is an estimation because 'cost basis' for futures is margin-based.
            h_margin_est = abs(h_qty) * 1200
            h_pct = (h_pnl / h_margin_est) * 100 if h_margin_est > 0 else 0.0
            
            hedge_context = f"""
            🛡️ ACTIVE HEDGE DETECTED:
            Instrument: {h_sym} (Qty: {h_qty})
            Hedge Delta: {h_delta:+.0f}
            Hedge P/L: ${h_pnl:.2f} ({h_pct:+.1f}%)
            """

        # Safe Extraction
        metrics = active_pos.get("account_metrics", {})
        acct_val = metrics.get("equity", 0)
        acct_pnl = metrics.get("unrealized_pnl", 0)
        acct_exp = metrics.get("exposure", 0)
        acct_exp_pct = metrics.get("exposure_pct", 0)
        
        ticker = active_pos.get("ticker", "N/A")
        
        # Normalize Ticker (If N/A or empty, set direction to NEUTRAL)
        ungrouped_legs = active_pos.get('ungrouped_positions', [])
        
        if not ticker or ticker == "N/A" or ticker == "HEDGED_PORTFOLIO":
            # [FIX] CHECK FOR SPREADS OR SINGLE LEGS BEFORE DEFAULTING TO NEUTRAL
            grouped_spreads = active_pos.get('grouped_positions', [])
            
            if grouped_spreads:
                # Promote the first spread to Primary Context
                priority_spread = grouped_spreads[0]
                ticker = f"{priority_spread.get('short_leg', '?')}/{priority_spread.get('long_leg', '?')}"
                direction = "SPREAD_STRATEGY" # Special Mode
                
                # [FIX] AGGREGATE PNL FOR MULTIPLE SPREADS
                total_pl = sum(s.get('net_pl', 0) for s in grouped_spreads)
                total_val = sum(s.get('net_val', 0) for s in grouped_spreads)
                # Calculate Cost Basis derived from Net Val - Net PL
                # Net Val = Cost + PL  => Cost = Net Val - PL
                total_cost = total_val - total_pl
                
                if abs(total_cost) > 0:
                    pos_pnl_pct = (total_pl / abs(total_cost)) * 100
                else:
                    pos_pnl_pct = 0.0
                    
                entry_price = 0.0 # Aggregate entry price is not single scalar
            elif ungrouped_legs:
                # [NEW] Single Legs Found
                ticker = f"PORTFOLIO ({len(ungrouped_legs)} LEGS)"
                direction = "PORTFOLIO_STRATEGY"
                # Use Portfolio Aggregates if available
                metrics = active_pos.get("account_metrics", {})
                pos_pnl_pct = metrics.get("pnl_pct", 0.0)
                entry_price = 0.0 # Not applicable for portfolio
            else:
                direction = "NEUTRAL"
                ticker = "NONE"
                pos_pnl_pct = 0.0
                entry_price = 0.0
        else:
            direction = "BULLISH" if active_pos.get("type") == "CALL" else "BEARISH"
            pos_pnl_pct = active_pos.get("pnl_pct", 0.0)
            entry_price = active_pos.get("avg_price", 0.0)

        print(f"DEBUG GREEKS KEYS: {list(greeks.keys())}")
        print(f"DEBUG HEDGE DATA: {hedge_data}")

        # [UPDATED] USE NET DELTA (Options + Hedge)
        delta_raw = greeks.get("net_delta", greeks.get("delta", "N/A"))
        delta = f"{delta_raw:+.0f}" if isinstance(delta_raw, (int, float)) else delta_raw
        print(f"DEBUG SELECTED DELTA: {delta} (Raw: {delta_raw})")
        gamma = greeks.get("gamma", "N/A") 
        theta = greeks.get("theta", "N/A")
        vega = greeks.get("vega", "N/A")
        iv = greeks.get("iv_contract", "N/A")

        # --- SPREAD & LEG DETECTION (NEW) ---
        # Check if the active position is part of a spread recognized by the dashboard
        active_pos_state = state.get('active_position', {})
        grouped_spreads = active_pos_state.get('grouped_positions', [])
        
        active_spread = None
        spread_context = "No Live Positions. Analyze Market Structure Only."
        
        # [FIX] Multi-Spread & Multi-Leg Aggregation Logic
        if direction in ["SPREAD_STRATEGY", "PORTFOLIO_STRATEGY"]:
             all_pos_text = []
             
             # 1. Add Spreads
             if grouped_spreads:
                 all_pos_text.append(f"📦 SPREADS ({len(grouped_spreads)}):")
                 for i, sp in enumerate(grouped_spreads):
                     net_pl = sp.get('net_pl', 0)
                     all_pos_text.append(f"   {i+1}. {sp.get('short_leg')}/{sp.get('long_leg')} | P/L: ${net_pl:.2f} ({sp.get('pl_pct',0):.1f}%)")

             # 2. Add Ungrouped Legs
             if ungrouped_legs:
                 all_pos_text.append(f"\n🧩 SINGLE LEGS ({len(ungrouped_legs)}):")
                 for i, leg in enumerate(ungrouped_legs):
                     l_sym = leg.get('ticker', '?')
                     l_qty = leg.get('qty', 0)
                     l_typ = leg.get('type', '?')
                     l_exp = leg.get('expiry', '?')
                     all_pos_text.append(f"   • {l_sym} ({l_typ} x{l_qty}) | Exp: {l_exp}")

             if all_pos_text:
                 spread_context = f"""
                    🔗 LIVE PORTFOLIO CONTEXT:
                    
                    {chr(10).join(all_pos_text)}
                    
                    --------------------------------
                    NET GREEKS (AGGREGATE):
                    Delta: {delta} | Gamma: {gamma} | Theta: {theta}
                    --------------------------------
                    
                    CRITICAL INSTRUCTION:
                    Analyze the Net Exposure (Greeks) relative to Market Structure.
                    Identify if we are fighting the trend or riding it.
                    """
             
             if grouped_spreads: active_spread = grouped_spreads[0] # Keep valid for downstream safety
             
        else:
            for spread in grouped_spreads:
                # Check if our ticker matches either leg
                if ticker == spread.get('short_leg') or ticker == spread.get('long_leg'):
                    active_spread = spread
                    spread_context = f"""
                    🔗 VERTICAL SPREAD DETECTED:
                    Short Leg: {active_spread.get('short_leg')}
                    Long Leg: {active_spread.get('long_leg')}
                    Net P/L: ${active_spread.get('net_pl', 0):.2f} ({active_spread.get('pl_pct', 0):.1f}%)
                    Net Value: ${active_spread.get('net_val', 0):.2f}
                    """
                    break

        # --- LOAD BODY & MIND ---
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_config.json")
        const_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gemini_constitution.json")
        thesis_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "spy_thesis.json") 
        
        config = safe_read_json(config_path)
        constitution_template = safe_read_json(const_path)
        config = safe_read_json(config_path)
        constitution_template = safe_read_json(const_path)
        thesis = safe_read_json(thesis_path)
        risk_profiles = safe_read_json(RISK_PROFILES_FILE) # [NEW] Load Risk Profiles
        
        # --- INJECT CONFIG INTO CONSTITUTION ---
        params = {}
        if config:
            params.update(config.get("active_trade", {}))
            params.update(config.get("indicators", {}))
        
        const_str = json.dumps(constitution_template, indent=2)
        for k, v in params.items():
            const_str = const_str.replace(f"{{{{{k}}}}}", str(v))
            
        constitution = json.loads(const_str)
        
        # --- SELECT STATE-DEPENDENT LOGIC ---
        logic_key = "NEUTRAL_POSITION"
        if "LONG" in direction.upper() or "BULL" in direction.upper(): logic_key = "LONG_POSITION"
        elif "SHORT" in direction.upper() or "BEAR" in direction.upper(): logic_key = "SHORT_POSITION"
        elif "SPREAD" in direction.upper(): logic_key = "NEUTRAL_POSITION"
        
        state_logic = constitution.get("state_dependent_logic", {}).get(logic_key, {})
        mission = state_logic.get("mission", "Analyze Market.")
        invalidation_rules = "\n".join([f"- {r}" for r in state_logic.get("invalidation_rules", [])])
        gex_logic = state_logic.get("gex_interpretation", {})

        # --- RISK PROFILE EXTRACTION ---
        # If 'active_position' has risk profile, use it. Usually it's in greeks_data structure.
        risk = active_pos.get("risk_profile", {})
        stop_loss = risk.get("stop_loss_price", "N/A")
        profit_target = risk.get("profit_target", "N/A")
        targets = risk.get("profit_targets", [])
        t1 = f"${targets[0]}" if len(targets) > 0 else "N/A"
        t2 = f"${targets[1]}" if len(targets) > 1 else "N/A"
        t3 = f"${targets[2]}" if len(targets) > 2 else "N/A"
        invalidation = risk.get("invalidation_condition", "N/A")
    
        # --- ACCOUNT METRICS EXTRACTION ---
        metrics = active_pos.get("account_metrics", {})
        exposure = metrics.get("exposure", "N/A")
        pnl = metrics.get("unrealized_pnl", "N/A")
        exposure_pct = metrics.get("exposure_pct", 0.0)
        pnl_pct = metrics.get("pnl_pct", 0.0)

        # --- LOAD WATCHTOWER ---
        watchtower_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_state_live.json")
        watchtower = safe_read_json(watchtower_path)
        wt_regime = watchtower.get("regime", "UNKNOWN")
        wt_alert = watchtower.get("alert_level", "UNKNOWN")
        wt_msg = watchtower.get("message", "No Data")
        
        # --- EXTRACT FLOW DETAILS ---
        sweeps = flow.get('sweeps', {})
        sweeps_prem = sweeps.get('total_premium', 0)
        sweeps_sent = sweeps.get('sentiment_scores', {})
        spy_sw_sent = sweeps_sent.get('SPY', 0)
        spx_sw_sent = sweeps_sent.get('SPX', 0)
        
        spx_flow = spx.get('flow_breakdown', {})
        d0_net = spx_flow.get('d0_net', 0)
        d1_net = spx_flow.get('d1_net', 0)
        
        # SPX Structure
        spx_levels = spx.get('levels', {})
        spx_call = spx_levels.get('call', 'N/A')
        spx_put = spx_levels.get('put', 'N/A')
        spx_pain = spx_levels.get('max_pain', 'N/A')
        spx_magnet = spx_levels.get('magnet', 'N/A')
        spx_zero = spx.get('zero_gamma', 'N/A')

        # --- EXTRACT SENTIMENT SCORES (NEW) ---
        # SPX Sentiment (From flow_stats)
        spx_d0_sent = spx_flow.get('d0_sent', 0)
        spx_d1_sent = spx_flow.get('d1_sent', 0)
        spx_cum = spx_flow.get('daily_cum_sent', "N/A")

        # SPY Sentiment (From Deep Flow)
        spy_deep = spy.get('deep_flow', {})
        spy_0dte_sent = spy_deep.get('0dte_sent', 0)
        spy_next_sent = spy_deep.get('next_expiry_sent', 0)
        spy_cum = spy_deep.get('daily_cum_sent', "N/A")

        # Helper to label sentiment
        def label_sent(score):
            if isinstance(score, str): return score
            if score > 5: return f"BULLISH BREADTH (+{score})"
            if score < -5: return f"BEARISH BREADTH ({score})"
            return f"NEUTRAL ({score})"

        # --- DYNAMIC CONTEXT (MECHANICAL LOGIC) ---
        # 1. SQUEEZE OVERRIDE
        if "BULL DIV" in str(hist_div) or "SQUEEZE" in str(wt_regime) or "BULL" in logic_key:
            trend_instruction = "MECHANICAL STATE: SHORT SQUEEZE. Buying Pressure > Selling Pressure. Bearish Flow is Squeeze Fuel (Forced Covering). Trust Price Authority > Flow Authority."
        
        # 2. STANDARD TREND (VWAP/SMA AUTHORITY)
        else:
            trend_instruction = f"MECHANICAL STATE: STANDARD. Analyze friction. Current Stack is {stack_status}. If Price > ${sma_20} and ${vwap}, Trend is BULLISH (Flow is likely Hedging). If Price < ${sma_20}, Trend is WEAK."

        # [FIX] Helper to sanitize JSON
        def clean_json_text(text):
            # Remove markdown wrapping
            text = text.replace("```json", "").replace("```", "").strip()
            return text

        # [NEW] Helper for Currency Formatting ($11.94m)
        def fmt_money(val):
            if not isinstance(val, (int, float)): return str(val)
            abs_val = abs(val)
            if abs_val >= 1_000_000_000:
                return f"${val/1_000_000_000:.2f}b"
            elif abs_val >= 1_000_000:
                return f"${val/1_000_000:.2f}m"
            elif abs_val >= 1_000:
                return f"${val/1_000:.2f}k"
            else:
                return f"${val:.2f}"

        # [NEW] Read Quant Bridge Data from STATE
        quant_analysis = state.get("quant_analysis", {})
        quant_context = "QUANT DATA: (Waiting for Snapshot...)"
        
        # [NEW] Strategic Narrative Extraction
        spx_regime = "N/A"
        if quant_analysis:
             quant_context = f"QUANT RISK ECOSYSTEMS:\n{json.dumps(quant_analysis, indent=2)}"
             spx_regime = quant_analysis.get("SPX", {}).get("regime", "N/A")
        
        # [FIX] Read from spx_profile (Profiler), not market_structure (Walls)
        spx_prof = state.get('spx_profile', {})
        spx_trajectory = spx_prof.get("trajectory", "Analyzing...")
        spx_magnet = spx_prof.get("magnet", "N/A")

        # [FIX] Pre-Format Variables to Avoid F-String Crashes
        def safe_float(v):
            try: return float(v)
            except: return 0.0
            
        try:
            acct_val_s = f"{safe_float(acct_val):,.2f}"
            acct_pnl_s = f"{safe_float(acct_pnl):.2f}"
            acct_exp_s = f"{safe_float(acct_exp):,.2f}"
            acct_exp_pct_s = f"{safe_float(acct_exp_pct):.1f}"
            entry_price_s = f"{safe_float(entry_price):.2f}"
            pos_pnl_pct_s = f"{safe_float(pos_pnl_pct):+.2f}"
        except Exception as e:
            print(f"⚠️ Formatting Error: {e}")
            acct_val_s = "0.00"
            acct_pnl_s = "0.00"
            acct_exp_s = "0.00"
            acct_exp_pct_s = "0.0"
            entry_price_s = "0.00"
            pos_pnl_pct_s = "+0.00"

        # [FIX] Extract Variables to Prevent F-String Complexity
        rp_str = json.dumps(risk_profiles, indent=2)
        
        l_spy_d0 = label_sent(spy_0dte_sent)
        l_spy_nx = label_sent(spy_next_sent)
        l_spy_cum = label_sent(spy_cum)
        l_spy_sw = label_sent(spy_sw_sent)
        
        l_spx_d0 = label_sent(spx_d0_sent)
        l_spx_cum = label_sent(spx_cum)
        l_spx_sw = label_sent(spx_sw_sent)
        
        f_spy_d0 = fmt_money(spy_0dte_val)
        f_spy_tot = fmt_money(spy_prof_delta)
        f_spx_d0 = fmt_money(d0_net)
        f_spx_nx = fmt_money(d1_net)
        f_sw_3d = fmt_money(net_flow_next)
        f_sw_0d = fmt_money(net_flow_0dte)
        f_sw_prem = fmt_money(sweeps_prem)
        
        mag_val = spy.get('vol_trigger', 'N/A')
        cw_val = spy.get('call_wall', 'N/A')
        pw_val = spy.get('put_wall', 'N/A')

        # [NEW] Direct Ingestion of History for Magnets
        NEXUS_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_history.json")
        history_direct = safe_read_json(NEXUS_HISTORY_FILE)
        
        magnets_context = "No Magnet Data"
        try:
             magnets = history_direct.get("structural_magnets", [])
             if magnets:
                 m_rows = []
                 for m in magnets:
                     # m = {'strike': 690, 'gex': 4200000000, 'expiry': '01/26'}
                     val_fmt = fmt_money(m.get('gex', 0))
                     m_rows.append(f"   * Level ${m.get('strike')}: {val_fmt} Net GEX (Exp: {m.get('expiry', '?')})")
                 magnets_context = "\n".join(m_rows)
        except Exception as e: magnets_context = f"Error reading magnets: {e}"

        # [NEW] SPY Structural Framework Ingestion
        spy_framework_txt = "Analyzing..."
        spy_framework_discord = ""
        try:
            spy_prof_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_spy_profile.json")
            if os.path.exists(spy_prof_path):
                spy_prof = safe_read_json(spy_prof_path)
                gex_struct = spy_prof.get("gex_structure", [])
                
                rows = []
                # 0DTE
                if len(gex_struct) > 0:
                     d0 = gex_struct[0]
                     d0_gex = fmt_money(d0.get('total_gamma', 0))
                     d0_pain = d0.get('max_pain_strike', 'N/A')
                     d0_poc = d0.get('volume_poc_strike', 'N/A')
                     d0_flip = d0.get('gex_flip_point', 'N/A')
                     
                     rows.append(f"   * 0DTE: Total GEX: {d0_gex} | Flip: ${d0_flip} | Pin (POC): ${d0_poc} | Pain: ${d0_pain}")
                     
                     # 0DTE Hedge Metrics
                     pc_vol = d0.get('pc_ratio_volume')
                     pc_oi = d0.get('pc_ratio_oi')
                     if pc_vol is not None and pc_oi is not None:
                         rows.append(f"   * [HEDGE METRICS] P/C Vol: {pc_vol:.2f} | P/C OI: {pc_oi:.2f}")
                
                # [NEW] Next Friday Logic (SPY)
                # Reuse target_friday_str from previous calculation (assumed in scope or re-calculated)
                # If scope is an issue, re-calc:
                try: 
                    target_friday_str = get_next_friday()
                except:
                    # Defining here if not in scope
                    def get_next_friday_spy():
                        today = datetime.datetime.now().date()
                        if today.weekday() < 4: days_ahead = 4 - today.weekday()
                        else: days_ahead = (7 - today.weekday()) + 4
                        target = today + datetime.timedelta(days=days_ahead)
                        return target.strftime('%Y-%m-%d')
                    target_friday_str = get_next_friday_spy()

                # Find the row matching next friday
                d1 = None
                d1_label = "NEXT"
                
                # Check gex_struct for matching expiry
                # Structure: [ {..., 'short_gamma_wall_above': {'expirDate': 'YYYY-MM-DD'} }, ... ]
                
                if len(gex_struct) > 1:
                    for item in gex_struct[1:]:
                        # Try to extract date from nested objects
                        try:
                            # Try wall objects first as they contain metadata
                            date_found = None
                            for key in ['short_gamma_wall_above', 'short_gamma_wall_below']:
                                obj = item.get(key)
                                if isinstance(obj, dict):
                                    date_found = obj.get('expirDate')
                                    if date_found: break
                            
                            if date_found == target_friday_str:
                                d1 = item
                                d1_label = f"NEXT (Friday {target_friday_str[5:]})"
                                break
                        except: pass
                
                # Fallback
                if not d1 and len(gex_struct) > 1:
                    d1 = gex_struct[1]
                    d1_label = "NEXT (Seq)"

                if d1:
                     d1_gex = fmt_money(d1.get('total_gamma', 0))
                     d1_pain = d1.get('max_pain_strike', 'N/A')
                     d1_poc = d1.get('volume_poc_strike', 'N/A')
                     d1_flip = d1.get('gex_flip_point', 'N/A')
                     rows.append(f"   * {d1_label}: Total GEX: {d1_gex} | Flip: ${d1_flip} | Pin: ${d1_poc} | Pain: ${d1_pain}")

                     # Next Expiry Hedge Metrics
                     pc_vol = d1.get('pc_ratio_volume')
                     pc_oi = d1.get('pc_ratio_oi')
                     if pc_vol is not None and pc_oi is not None:
                         rows.append(f"   * [HEDGE METRICS] P/C Vol: {pc_vol:.2f} | P/C OI: {pc_oi:.2f}")
                
                if rows:
                    spy_framework_txt = "\n".join(rows)
                    spy_framework_discord = "```" + "\n".join(rows).replace("   * ", "• ") + "```"
            else:
                 spy_framework_txt = "No SPY Profile Data Found"
        except Exception as e:
            spy_framework_txt = f"Error reading SPY Framework: {e}"

        # [NEW] Technical Context Logic (Support vs Resistance)
        tech_context_lines = []
        try:
            curr_px = safe_float(spy_price)
            
            def check_lvl(name, val_str):
                v = safe_float(val_str)
                if v <= 0: return f"{name}: N/A"
                if curr_px > v: return f"{name} ${v:.2f} (SUPPORT)"
                return f"{name} ${v:.2f} (RESISTANCE)"

            tech_context_lines.append(f"VWAP: {check_lvl('VWAP', vwap)}")
            tech_context_lines.append(f"SMA20: {check_lvl('SMA20', sma_20)}")
            tech_context_lines.append(f"SMA50: {check_lvl('SMA50', sma_50)}")
            tech_context_lines.append(f"SMA200: {check_lvl('SMA200', sma_200)}")
            
            tech_block = " | ".join(tech_context_lines)
        except: tech_block = "Technical Logic Failed"

        # --- ANALYST PERSONA PROMPT ---
        prompt = f'''
        SYSTEM PROMPT:
        You are a Senior Market Structure Analyst. 
        Your goal is NOT to advise on buying/selling. 
        Your goal is to EXPLAIN the mechanics driving the current price action.
        
        INSTRUCTION:
        {trend_instruction}
        CRITICAL: YOU MUST CITE SPECIFIC PRICE LEVELS. Do not say "at the wall", say "at the Call Wall ($5850)". Do not say "above VWAP", say "above VWAP ($5815)".
        MANDATORY: You MUST reference at least one level from 'TECHNICAL STRUCTURE' (Support/Resistance) in your narrative.
        
        MANDATORY GEX PHYSICS (DO NOT HALLUCINATE):
        1. POSITIVE GEX (> $0): Dealers are LONG GAMMA. They buy dips and sell rips. This PINS price and REDUCES volatility. (Stability).
        2. NEGATIVE GEX (< $0): Dealers are SHORT GAMMA. They sell dips and buy rips. This EXPANDS volatility and accelerates moves. (Instability).
        3. IF Total GEX is NEGATIVE, you MUST NOT call the market "Stable". It is "Fragile" or "Volatile".

        DATA INGESTION:
        1. PRICE: ${spy_price} (Trend Context: {tape_mom})
        2. TECHNICAL STRUCTURE (PRICE vs LEVELS):
           - Stack: {stack_status} ({extension})
        2. TECHNICAL STRUCTURE (PRICE vs LEVELS):
           - Stack: {stack_status} ({extension})
           - Analysis: {tech_block}
           - VOLUME INTELLIGENCE (RVOL & FORCE):
             * SPY: Day RVOL {rvol:.2f} | Current Hour RVOL {h_rvol:.2f}
             * SPX: Day RVOL {spx_rvol:.2f} | Current Hour RVOL {spx_h_rvol:.2f}
             * FORCE INDEX (13-EMA): {fi_13:+.2f} (Swing Conviction)
             * TREND STRENGTH: {trend_str:.0f}/100 
             (Logic: RVOL > 1.5 = Expansion. Force Index > 0 = Bullish Pressure. Strength > 80 = Strong Trend).
        3. SPX STRUCTURAL FRAMEWORK (0DTE vs Next):
           {gex_framework}
        4. SPY STRUCTURAL FRAMEWORK (In-Depth GEX):
           {spy_framework_txt}
           
        5. STRUCTURE (GEX LEVELS): 
           - Magnet: {mag_val}
           - Call Wall: {cw_val}
           - Put Wall: {pw_val}
           - Max Pain: {spx_pain}
        5. MONEY FLOW ANALYTICS (GRANULAR NET DELTA):
           --------------------------------------------------
           A. SPY PROFILER (The ETF Itself):
              - 0DTE Flow: {f_spy_d0}
              - Total Flow: {f_spy_tot}
           
           B. SPX PROFILER (The Index):
              - 0DTE Flow: {f_spx_d0}
              - Next Expiry Flow: {f_spx_nx}
           
           C. SWEEPS V2 (Smart Money):
              - 3DTE+ (Strategic): {f_sw_3d}
              - 0DTE (Tactical): {f_sw_0d}
              - Total Premium: {f_sw_prem}
           --------------------------------------------------
           INTERPRETATION: 
           - Convergence (All Green/Red) = STRONG SIGNAL. 
           - Divergence (SPY Green, SPX Red) = CHOP/HEDGING.

        5. SENTIMENT (BREADTH - TRADER CONVICTION):
           * Definition: "Sentiment" tracks the COUNT of Bullish vs Bearish Tags.
           * "Instant": 5-minute snapshot of aggression.
           * "Cumulative": Day-long accumulation of conviction.
           
           * SPY 0DTE Sentiment (Inst): {label_sent(spy_0dte_sent)}
           * SPY Trend Sentiment (Inst): {label_sent(spy_next_sent)}
           * [NEW] SPY CUMULATIVE: {label_sent(spy_cum)}
           * [NEW] SPY SWEEPS FEED: {label_sent(spy_sw_sent)} (Raw Flow Count)
           
           * SPX 0DTE Sentiment (Inst): {label_sent(spx_d0_sent)}
           * [NEW] SPX CUMULATIVE: {label_sent(spx_cum)}
           * [NEW] SPX SWEEPS FEED: {label_sent(spx_sw_sent)} (Raw Flow Count)

           * [HEDGE CONTEXT] P/C Ratios (Index):
             - Volume Ratio: {pc_vol:.2f} 
             - OI Ratio: {pc_oi:.2f}
             (Note: High P/C (>1.0) often implies Dealer Long Gamma or Institutional Hedging. This can SUPPORT price.)

           INTERPRETATION LOGIC (DIVERGENCE):
           - IF Cumulative is HIGH (+50) but Net Premium is NEGATIVE: Retail is buying the dip, Whales are selling. (Distribution).
           - IF Cumulative is LOW (-50) but Net Premium is POSITIVE: Retail is panic selling, Whales are absorbing. (Accumulation).
           - IF Cumulative and Premium match: Trend is Healthy.

        6. MARKET STRUCTURE MAGNETS (TIMELINE CONTEXT):
           {magnets_context}
           * INTERPRETATION:
           * These are the strongest Gamma levels in the market.
           * Note the EXPIRATION. 0DTE magnets must be resolved TODAY. Later expiries act as longer-term gravitation.

        7. QUANT RISK VECTORS (NEW):
           {quant_context}
           * Use this to identify if we are in a "WHALE STABILITY" or "RETAIL INSTABILITY" regime.
           * "instability_ratio" > 5.0 indicates high probability of a squeeze or move.
        
        GREEK PROFILING & RECOMMENDATION PROTOCOL (NEW)
        Objective: Compare the user's CURRENT Portfolio Greeks against the OPTIMAL Greeks based on market condition.
        
        Available Profiles:
        {json.dumps(risk_profiles, indent=2)}
        
        Step 1: Diagnose Market Sentiment
        Select ONE profile from the list above that best matches the current environment (e.g., "BEARISH > cautious_top").
        
        Step 2: Perform Gap Analysis
        - Delta Gap: User Net Delta vs Target Delta.
        - Gamma Gap: User Net Gamma vs Target Gamma.
        
        Step 3: Generate Recommendation
        Prescribe a specific action from the "strategy" field of the selected profile.
        
        Step 4: Formulate the Fix
        When generating the "Actionable Fix", you MUST prefix the recommendation with the numeric targets from the selected profile.
        * Format: `[Target Delta: x to y | Target Gamma: x to y] -> Recommendation`

        TRAP ANALYSIS CROSS-CHECK PROTOCOL (NEW)
        Step 1: Analyze Trapped Positioning
        - TRAPPED BEARS: Potential Buying Pressure (Squeeze Fuel). Bias: BULLISH.
        - TRAPPED BULLS: Potential Selling Pressure (Liquidation). Bias: BEARISH.
        
        Step 2: Compare Traps vs Greek Profile
        Step 3: If Divergent, Issue WARNING.
        
        ANALYSIS PROTOCOL:
        - CONFLICT RESOLUTION: If Price is Rising but Flow is Bearish, check the TECHNICALS. If Price > VWAP, the Flow is likely Hedging.
        - GREEK TRANSLATION: Explain the mechanics. (e.g. "High Theta requires velocity").
        - TRAP DETECTION: Who is underwater? Bulls or Bears?
        - HEDGE CONTEXT: If Ticker is 'HEDGED_PORTFOLIO', treat it as a unified SPY position for Greek Gap analysis.
        
        HOLDINGS CONTEXT:
        Account Value: ${acct_val_s}
        Account P/L: ${acct_pnl_s} (Unrealized)
        Account Exposure: ${acct_exp_s} ({acct_exp_pct_s}%)

        LIVE POSITION CONTEXT:
        We are holding {direction} on {ticker} from ${entry_price_s}. 
        Current P/L: {pos_pnl_pct_s}%.
        {hedge_context}
        
        {spread_context}
        
        OUTPUT FORMAT (JSON ONLY)
        {{
          "market_regime": "One of: RALLY, SELLOFF, CHOP, REVERSAL_UP, REVERSAL_DOWN",
          "primary_driver": "What is moving the market?",
          "market_diagnosis": "Must match a key from 'greek_calibration_profiles' (e.g., 'range_chop')",
          "trap_check": "Brief analysis of trapped traders vs profile.",
          "greek_gap": {{
             "delta_status": "Brief status (e.g., OVER_EXPOSED)",
             "gamma_status": "Brief status (e.g., FRAGILITY_RISK)"
          }},
          "key_friction_levels": "Where will price stall?",
          "narrative": "A 2-3 sentence breakdown logic.",
          "action": "HOLD | HEDGE | CLOSE_IMMEDIATELY",
          "actionable_fix": "[Target Delta: min to max | Target Gamma: min to max] -> Specific strategy recommendation to bridge the gap",
          "win_probability": "0-100%",
          "primary_threat": "The single biggest risk factor"
        }}
        '''
        
        print("-" * 50)
        print("🔍 AUDITOR VISION (What Gemini Sees):")
        print(f"TICKER: {ticker} | DIRECTION: {direction}")
        print(f"ENTRY: ${entry_price:.2f} | POS P/L: {pos_pnl_pct:+.2f}%")
        print(f"ACCT P/L: ${pnl} ({pnl_pct:.2f}%) | EXPOSURE: ${exposure} ({exposure_pct:.1f}%)")
        print(f"GREEKS: Delta:{delta} | Gamma:{gamma} | Theta:{theta} | Vega:{vega} | IV:{iv}%")
        print(f"RISK: Stop:${stop_loss} | T1:{t1} | T2:{t2} | T3:{t3}")
        if hedge_context:
            print(f"🔰 HEDGE ACTIVE: {hedge_context.strip()}")
        if grouped_spreads:
            print(f"🔗 SPREAD PORTFOLIO ({len(grouped_spreads)} LEGS):")
            for i, sp in enumerate(grouped_spreads):
                print(f"   {i+1}. {sp['short_leg']}/{sp['long_leg']} (Net P/L: {sp.get('pl_pct', 0):.1f}%)")
        elif active_spread:
             print(f"🔗 SPREAD: {active_spread['short_leg']}/{active_spread['long_leg']} (Net P/L: {active_spread.get('pl_pct', 0):.1f}%)")
        print("-" * 50)
        print(f"📊 GEX FRAMEWORK INJECTED:\n{gex_framework}")
        print("-" * 50)
        
        print(f"🤖 Consulting Gemini ({direction} Mode)...")
        try:
            # [ROBUST] Retry Logic
            response = None
            for attempt in range(3):
                try:
                    response = model.generate_content(
                        prompt,
                        generation_config={"response_mime_type": "application/json"},
                        request_options={'timeout': 120} # Increased to 120s
                    )
                    break
                except Exception as api_e:
                    if "504" in str(api_e) or "timeout" in str(api_e).lower() or "500" in str(api_e):
                        print(f"⚠️ API Timeout/Error (Attempt {attempt+1}/3). Retrying...")
                        time.sleep(2)
                    else: raise api_e
            
            if not response: raise Exception("API Failed after retries")
            
            clean_text = clean_json_text(response.text)
            analysis = json.loads(clean_text)
            
            print("-" * 50)
            print("🧠 GEMINI BRAIN OUTPUT:")
            print(json.dumps(analysis, indent=2))
            print("-" * 50)
            
            # --- ALERT LOGIC ---
            action = analysis.get("action", "HOLD").upper()
            prob = analysis.get("win_probability", "N/A")
            threat = analysis.get("primary_threat", analysis.get("anomaly_detection", "None"))
            reason = analysis.get("narrative", analysis.get("reasoning", "No narrative provided"))
            
            msg_text = f"**Verdict:** {action} ({prob})\n**Conflict:** {threat}\n**Narrative:** {reason}"
            
            if system_status != "OPERATIONAL":
                msg_text = f"⚠️ [{system_status}] {msg_text}"
                
                # DIAGNOSTICS REPORT
                data_quality = state.get("data_quality", {})
                debug_lines = []
                for k, v in data_quality.items():
                    if v.get("status") != "ONLINE":
                        debug_lines.append(f"• **{k}:** ❌ {v.get('status')} ({v.get('error', 'Unknown')})")
                    else:
                        debug_lines.append(f"• **{k}:** ✅ ONLINE")
                        
                debug_text = "\n".join(debug_lines)
                msg_text += f"\n\n**🔧 SYSTEM DIAGNOSTICS:**\n{debug_text}"
            
            alert_color = 3447003 # Blue
            if "CLOSE" in action: alert_color = 15158332 # Red
            elif "HEDGE" in action: alert_color = 16776960 # Yellow
            elif "HOLD" in action: alert_color = 5763719 # Green

            # --- CONSTRUCT DISCORD FIELDS ---
            discord_fields = []
            
            # Field 1: Position Core
            if direction != "NEUTRAL":
                pos_val = f"{direction} {ticker}"
                if entry_price > 0: pos_val += f"\nEntry: ${entry_price:.2f}"
                
                if grouped_spreads:
                    pos_val += f"\n({len(grouped_spreads)} Spreads)"
                    # List individual legs (up to 5)
                    for sp in grouped_spreads[:5]:
                        pos_val += f"\n• {sp['short_leg']}/{sp['long_leg']} ({sp.get('pl_pct', 0):.1f}%)"
                    if len(grouped_spreads) > 5:
                        pos_val += f"\n...(+{len(grouped_spreads)-5} more)"
                
                if hedge_context:
                    # Clean up identifier for embed
                    hc_clean = hedge_context.replace("🛡️ ACTIVE HEDGE DETECTED:", "").strip()
                    pos_val += f"\n\n🛡️ **HEDGE:**\n{hc_clean}"

                discord_fields.append({"name": "🎯 Position", "value": pos_val, "inline": True})
                
                # Field 2: Performance
                perf_val = f"P/L: {pos_pnl_pct:+.2f}%\nAcct: {pnl_pct:+.2f}%"
                discord_fields.append({"name": "💰 Performance", "value": perf_val, "inline": True})
                
                # Field 3: Risk/Greeks
                # Field 3: Risk/Greeks
                d_label = "Net Delta" if hedge_data else "Delta"
                greeks_val = f"{d_label}: {delta}\nGamma: {gamma}\nTheta: {theta}"
                discord_fields.append({"name": "⚡ Greeks", "value": greeks_val, "inline": True})
            
            # [NEW] SPY Structural Framework Injected


            # --- [NEW] HEALTH AUDIT BLOCK ---
            diagnosis = analysis.get("market_diagnosis", "N/A")
            trap_check = analysis.get("trap_check", "N/A")
            gap = analysis.get("greek_gap", {})
            d_status = gap.get("delta_status", "?")
            g_status = gap.get("gamma_status", "?")
            fix = analysis.get("actionable_fix", "N/A")

            # [NEW] ENFORCE NUMERIC TARGETS (Python Override)
            if diagnosis != "N/A" and "Target Delta" not in fix:
                try:
                    r_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk_profiles.json")
                    if os.path.exists(r_path):
                        with open(r_path, 'r') as f:
                            r_data = json.load(f)
                            all_profs = r_data.get("greek_calibration_profiles", {})
                            
                            # Search for diagnosis key (Fuzzy Search)
                            target_str = ""
                            found_profile = None
                            
                            for sentiment in all_profs.values():
                                for key, profile in sentiment.items():
                                    # 1. Direct Key Match
                                    if diagnosis.lower() == key.lower():
                                        found_profile = profile
                                        break
                                    # 2. Description Match
                                    if diagnosis.lower() in profile.get('description', '').lower():
                                        found_profile = profile
                                        break
                                if found_profile: break
                            
                            if found_profile:
                                 td = found_profile.get('target_delta', ['?', '?'])
                                 tg = found_profile.get('target_gamma', ['?', '?'])
                                 target_str = f"[Target Delta: {td[0]} to {td[1]} | Target Gamma: {tg[0]} to {tg[1]}]"
                            
                            if target_str:
                                fix = f"**{target_str}** -> {fix}"
                except Exception as e:
                    print(f"Error injecting targets: {e}")

            align_icon = "✅" if "OK" in d_status and "OK" in g_status else "⚠️"
            if "WRONG" in d_status: align_icon = "🚨"
            
            audit_val = f"**Diagnosis:** {diagnosis}\n**🪤 Structural:** {trap_check}\n**Current Positioning:** Delta: `{delta}` | Gamma: `{gamma}`\n**Status:** {align_icon} Delta:{d_status} | Gamma:{g_status}\n**Fix:** {fix}"
            audit_val = f"**Diagnosis:** {diagnosis}\n**🪤 Structural:** {trap_check}\n**Current Positioning:** Delta: `{delta}` | Gamma: `{gamma}`\n**Status:** {align_icon} Delta:{d_status} | Gamma:{g_status}\n**Fix:** {fix}"
            discord_fields.append({"name": "🛡️ Portfolio Health Audit", "value": audit_val, "inline": False})

            # [NEW] STRATEGIC NARRATIVE
            s_regime = str(spx_regime) if spx_regime else "N/A"
            s_traj = str(spx_trajectory) if spx_trajectory else "Calculating..."
            
            strat_val = f"**Regime:** {s_regime}\n**{s_traj}**"
            # Ensure not empty and not too long
            if len(strat_val) > 1000: strat_val = strat_val[:1000] + "..."
            
            discord_fields.append({"name": "Strategic Narrative", "value": strat_val, "inline": False})
            
            # [NEW] GEX STRUCTURE VISUALIZATION
            if gex_framework and "No GEX" not in gex_framework:
                gex_display = gex_framework.replace("   *", "•").strip()
                discord_fields.append({"name": "🏗️ SPX Structural Framework", "value": f"```{gex_display}```", "inline": False})

            # [NEW] SPY Structural Framework (Relocated)
            if spy_framework_discord:
                 discord_fields.append({"name": "🏗️ SPY Structural Framework", "value": spy_framework_discord, "inline": False})

            # [NEW] MONEY FLOW VISUALIZATION (Requested by User)
            flow_val = f"**SPY (ETF):** 0DTE: `{fmt_money(spy_0dte_val)}` | Total: `{fmt_money(spy_prof_delta)}`\n"
            flow_val += f"**SPX (Idx):** 0DTE: `{fmt_money(d0_net)}` | Next: `{fmt_money(d1_net)}`\n"
            flow_val += f"**SWEEPS (NET PREMIUM):** 0DTE: `{fmt_money(net_flow_0dte)}` | 3DTE+: `{fmt_money(net_flow_next)}`"
            discord_fields.append({"name": "🌊 Money Flow Analytics", "value": flow_val, "inline": False})



            # [NEW] VOLUME INTELLIGENCE
            def rvol_desc(val):
                if val >= 2.0: return "🔥 IGNITION"
                if val >= 1.5: return "⚡ ACTIVE"
                if val < 0.7: return "💤 WEAK"
                return "NORMAL"

            vol_val =  f"**SPY:** Day `{rvol:.2f}` | Hr `{h_rvol:.2f}` ({rvol_desc(h_rvol)})\n"
            vol_val += f"**SPX:** Day `{spx_rvol:.2f}` | Hr `{spx_h_rvol:.2f}` ({rvol_desc(spx_h_rvol)})\n"
            vol_val += f"**Force Index:** `{fi_13:+.2f}` | **Strength:** `{trend_str:.0f}/100`"
            
            discord_fields.append({"name": "🔊 Volume Intelligence (RVOL)", "value": vol_val, "inline": False})

            # [NEW] VRP INTELLIGENCE (User Request)
            try:
                VRP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nexus_vrp_context.json")
                if os.path.exists(VRP_FILE):
                    vrp_ctx = safe_read_json(VRP_FILE)
                    # "iv30": 0.12, "hv30": 0.10, "vrp_spread": 0.02
                    iv30 = vrp_ctx.get('iv30', 0)
                    hv30 = vrp_ctx.get('hv30', 0)
                    spread = vrp_ctx.get('vrp_spread', 0)
                    
                    # Formatting
                    vrp_color = "🟢" if spread > 0 else "🔴"
                    sig_text = "SELL PREMIUM (Risk Overpriced)" if spread > 0 else "BUY PREMIUM (Risk Underpriced)"
                    
                    vrp_val = f"**Spread:** `{spread*100:+.2f}%` (IV30: {iv30*100:.1f}% - HV30: {hv30*100:.1f}%)\n"
                    vrp_val += f"**Signal:** {vrp_color} {sig_text}"
                    
                    discord_fields.append({"name": "⚡ Volatility Risk Premium (VRP)", "value": vrp_val, "inline": False})
            except Exception as e:
                print(f"VRP Extract Error: {e}")

            # [NEW] VISUAL PROOF OF SENTIMENT LOGIC
            def fmt_score(x):
                try: return f"{int(x):+d}"
                except: return str(x)

            sent_val = f"**SPX Breadth =** `{fmt_score(spx_cum)}`     **Sweeps =** `{fmt_score(spx_sw_sent)}`\n"
            sent_val += f"**SPY Breadth =** `{fmt_score(spy_cum)}`     **Sweeps =** `{fmt_score(spy_sw_sent)}`"
            discord_fields.append({"name": "🌊 Market Breadth (Sentiment)", "value": sent_val, "inline": False})

            self.send_alert(msg_text, color=alert_color, fields=discord_fields)

        except Exception as e:
            print(f"❌ Gemini API Error: {e}")

    def send_alert(self, text, color, fields=None):
        # Wrapper for send_discord_msg to handle pinning logic
        # if text == self.last_sent_msg and self.last_message_id:
        #    print(f"🔁 Status Unchanged. Skipping Edit.")
        #    return

        #    return
        
        print(f"DEBUG FIELDS: {json.dumps(fields, default=str)}")
        print(f"📤 Sending Alert (Fresh Message)...")
        # [MOD] Force fresh message every time (User Request)
        # We pass message_id=None to ensure a NEW message is sent instead of editing the old one.
        new_id = send_discord_msg(text, color=color, message_id=None, fields=fields)
        
        # We do NOT update self.last_message_id for editing purposes anymore,
        # but we can track it if needed for other logic (unlikely).
        # self.last_message_id = new_id 
        self.last_sent_msg = text

if __name__ == "__main__":
    print("🚀 Starting Gemini Analyst (Gentle Mode)...")
    send_discord_msg("🚀 **Gemini Analyst Online.**\nSystem Repair Complete. Monitoring...", color=3447003)
    
    auditor = MarketAuditor()
    
    try:
        while True:
            # --- DYNAMIC SCHEDULING LOGIC ---
            tz = pytz.timezone('US/Eastern')
            now = datetime.datetime.now(tz)
            
            # Determine Interval
            is_weekday = now.weekday() < 5
            market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
            is_market_hours = is_weekday and (market_open <= now <= market_close)
            
            if is_market_hours:
                sleep_seconds = 3600 # 1 Hour
                mode = "MARKET_HOURS"
            # [FIX] Expanded Buffer: 06:00 - 18:00 to catch 6:30 AM runs and prevent oversleeping the Open
            elif is_weekday and 6 <= now.hour <= 18:
                sleep_seconds = 3600
                mode = "PRE_POST_BUFFER"
            else:
                # [FIX] INCREASED to 4 Hours per User Request
                sleep_seconds = 14400 
                mode = "OFF_HOURS"
            
            # Run Analysis
            try:
                print(f"⏱️ Cycle Start ({mode}) at {now.strftime('%H:%M:%S ET')}")
                # HEARTBEAT
                try:
                    with open("auditor_pulse", "w") as f: f.write(str(time.time()))
                except: pass
                
                auditor.run_cycle()
            except Exception as e:
                print(f"Loop Error: {e}")
                import traceback
                traceback.print_exc()
            
            # [FIX] Align to Hour (00) for Consistency
            if is_market_hours or mode == "PRE_POST_BUFFER":
                # Calculate next hour mark
                target_dt = now.replace(minute=0, second=0, microsecond=0) + datetime.timedelta(hours=1)
                
                sleep_seconds = (target_dt - now).total_seconds()
                
                # If less than 1 minute remains, skip to NEXT interval to prevent double-firing
                if sleep_seconds < 60:
                    sleep_seconds += 3600
            
            # Off-hours logic remains simple Sleep
            
            next_run = now + datetime.timedelta(seconds=sleep_seconds)
            print(f"💤 Sleeping {sleep_seconds/60:.1f}m. Next Alignment: {next_run.strftime('%H:%M:%S ET')}")
            time.sleep(sleep_seconds)
            
    except KeyboardInterrupt:
        print("\n🛑 Auditor Stopped by User.")
        send_discord_msg("🛑 **Gemini Analyst Stopped.**", color=15158332)
