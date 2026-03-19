import nexus_lock
nexus_lock.enforce_singleton()
import google.generativeai as genai
import os
import time
import datetime
import requests
import json
import pytz

# --- CONFIGURATION ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
MODEL_NAME = 'gemini-2.5-flash' 
MAX_DATA_AGE = 3600 # 1 Hour
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MARKET_STATE_FILE = os.path.join(SCRIPT_DIR, "market_state.json")
THESIS_FILE = os.path.join(SCRIPT_DIR, "spy_thesis.json")
STRUCTURE_FILE = os.path.join(SCRIPT_DIR, "nexus_structure.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "market_config.json")
CONST_FILE = os.path.join(SCRIPT_DIR, "gemini_constitution.json")

from nexus_config import DISCORD_WEBHOOK_URL, ZMQ_PORT_NOTIFICATIONS

# --- SETUP GEMINI ---
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(MODEL_NAME)

# --- ZMQ SETUP ---
import zmq
ctx_audit = zmq.Context()
sock_audit = ctx_audit.socket(zmq.PUSH)
sock_audit.connect(f"tcp://localhost:{ZMQ_PORT_NOTIFICATIONS}")

def safe_read_json(filepath):
    if not os.path.exists(filepath): return {}
    try:
        with open(filepath, "r") as f: return json.load(f)
    except: return {}

def send_discord_msg(text, color=None, message_id=None):
    try:
        color_val = color if color else 3447003
        payload = {"title": "🧠 Gemini Market Auditor", "message": text, "color": color_val, "topic": "GEMINI_AUDITOR", "message_id": message_id}
        sock_audit.send_json(payload, flags=zmq.NOBLOCK)
        return "ZMQ_HANDLED"
    except: return None

class MarketAuditor:
    def __init__(self):
        self.last_sent_msg = None
        self.last_message_id = None 

    def run_cycle(self):
        print(f"📉 Reading Market State from {MARKET_STATE_FILE}...")
        state = safe_read_json(MARKET_STATE_FILE)
        if not state: return

        # --- SYSTEM HEALTH ---
        system_status = state.get("global_system_status", "UNSAFE")
        feed_health = state.get("feed_health", {})
        if system_status == "CRITICAL_OFFLINE":
             self.send_alert("**⛔ SYSTEM HALT: ALL FEEDS OFFLINE**", color=15158332)
             return

        # --- EXTRACT DATA ---
        mkt = state.get('market_structure', {})
        spy = mkt.get('SPY', {})
        spx = mkt.get('SPX', {})
        flow = state.get('flow_sentiment', {})
        history = state.get("historical_context", {})
        
        # --- POSITION DETECTION OVERHAUL ---
        active_pos = state.get("active_position", {})
        grouped_spreads = active_pos.get("grouped_positions", [])
        active_trade = active_pos.get("active_trade", {})
        
        # Determine Primary Context
        ticker = active_pos.get("ticker", "N/A")
        direction = "NEUTRAL"
        pos_pnl_pct = 0.0
        entry_price = 0.0
        
        spread_context = "" # Text to inject into prompt
        
        # If 'active_pos' top-level is empty, check spreads
        if (not ticker or ticker == "N/A") and grouped_spreads:
            # We have spreads but no single 'active' ticker context. 
            # Let's derive context from the BIGGEST spread or just the first one.
            primary_spread = grouped_spreads[0] # Naive first choice
            
            ticker = "SPREAD_GROUP"
            direction = "HEDGED"
            
            # Sum up Net P/L of all spreads
            total_spread_pl = sum([s.get('net_pl', 0) for s in grouped_spreads])
            total_spread_val = sum([s.get('net_val', 0) for s in grouped_spreads])
            
            # Simple P/L % calc (avoid div zero)
            pos_pnl_pct = 0.0 # Hard to calc % on net debit/credit mix without initial cost tracking here
            
            spread_lines = []
            for s in grouped_spreads:
                sl = s.get('short_leg', '?')
                ll = s.get('long_leg', '?')
                pl = s.get('net_pl', 0)
                spread_lines.append(f"- {sl}/{ll} (P/L: ${pl:.0f})")
                
            spread_context = f"""
            🔗 SPREAD PORTFOLIO DETECTED ({len(grouped_spreads)} Active):
            {chr(10).join(spread_lines)}
            Total Spread P/L: ${total_spread_pl:.0f}
            
            CRITICAL INSTRUCTION:
            The user is holding a portfolio of spreads. Some may be hedges for others.
            Analyze the market assuming we are managing this complex book.
            """
        elif ticker and ticker != "N/A":
             # Legacy/Single Leg Logic
             direction = "BULLISH" if active_pos.get("type") == "CALL" else "BEARISH"
             pos_pnl_pct = active_pos.get("pnl_pct", 0.0)
             entry_price = active_pos.get("avg_price", 0.0)

        # --- GREEKS ---
        greeks = active_pos.get("greeks", {})
        delta = greeks.get("delta", "N/A"); gamma = greeks.get("gamma", "N/A")
        theta = greeks.get("theta", "N/A"); vega = greeks.get("vega", "N/A")

        # --- ACCOUNT METRICS ---
        metrics = active_pos.get("account_metrics", {})
        pnl = metrics.get("unrealized_pnl", 0)
        exposure = metrics.get("exposure", 0)

        # --- PROMPT CONSTRUCTION ---
        spy_price = spy.get('price', 0)
        vwap = spy.get('trend_metrics', {}).get('vwap', 0)
        
        quant = state.get("quant_analysis", {})
        quant_str = json.dumps(quant, indent=2) if quant else "Wait for Snapshot..."
        
        # [FIX] Explicitly extract the Regimes that Gemini was missing from the raw block
        spx_regime = quant.get("SPX", {}).get("regime", "UNKNOWN")
        spy_regime = quant.get("SPY", {}).get("regime", "UNKNOWN")

        prompt = f'''
        SYSTEM PROMPT: You are a Senior Market Structure Analyst.
        
        LIVE POSITION:
        Ticker: {ticker} | Direction: {direction}
        Portfolio P/L: ${pnl} | Exposure: ${exposure}
        Greeks: Delta {delta} | Gamma {gamma} | Theta {theta}
        
        {spread_context}
        
        MARKET DATA:
        SPY Price: ${spy_price} (VWAP: ${vwap})
        SPX Max Pain: {spx.get('levels',{}).get('max_pain','N/A')}
        Net Flow: {flow.get('sweeps',{}).get('total_premium', 0)}
        
        QUANT RISK:
        SPX Market Regime: {spx_regime}
        SPY Market Regime: {spy_regime}
        {quant_str}
        
        TASK:
        Explain the mechanics moving price. Focus on the conflict between Flow, Structure (levels), our Position, and specifically the Market Regimes (e.g. are we in WHALE STABILITY or RETAIL INSANITY).
        
        OUTPUT (JSON):
        {{
          "market_regime": "CHOP | TREND | SQUEEZE",
          "primary_driver": "Short phrase",
          "narrative": "2-3 sentences max. Cite prices.",
          "action": "HOLD | CLOSE | HEDGE",
          "win_probability": "0-100%",
          "primary_threat": "Biggest risk to our position"
        }}
        '''

        # --- GENERATE ---
        print("-" * 50)
        print(f"🔍 AUDITOR VISION (Position-Aware):")
        if spread_context:
            print(spread_context)
        else:
            print(f"TICKER: {ticker} | DIRECTION: {direction}")
            print(f"ENTRY: ${entry_price:.2f} | P/L: {pos_pnl_pct:.2f}%")
        
        print(f"GREEKS: Delta {delta} | Gamma {gamma} | Theta {theta}")
        print("-" * 50)

        print(f"🤖 Consulting Gemini ({direction})...")
        try:
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            text = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            
            print("-" * 50)
            print("🧠 GEMINI BRAIN OUTPUT:")
            print(json.dumps(data, indent=2))
            print("-" * 50)
            
            # --- FORMAT MESSAGE ---
            act = data.get("action", "HOLD")
            narr = data.get("narrative", "")
            threat = data.get("primary_threat", "")
            
            msg = f"**Verdict:** {act}\n**Narrative:** {narr}\n**Threat:** {threat}"
            if spread_context: msg += f"\n\n*Managing {len(grouped_spreads)} Spreads*"
            
            color = 5763719 # Green
            if "CLOSE" in act: color = 15158332 # Red
            
            self.send_alert(msg, color)
            
        except Exception as e:
            print(f"❌ Gemini Error: {e}")

    def send_alert(self, text, color):
        if text == self.last_sent_msg and self.last_message_id: return
        print(f"📤 Sending Alert...")
        nid = send_discord_msg(text, color=color, message_id=self.last_message_id)
        if nid: self.last_message_id = nid; self.last_sent_msg = text

if __name__ == "__main__":
    print("🚀 Gemini Auditor 2.0 (Position-Aware) Online")
    auditor = MarketAuditor()
    send_discord_msg("✅ **Gemini Auditor Repatched & Online**\nMonitoring for positions...", color=3447003)
    
    while True:
        try:
            # --- SCHEDULE ---
            tz = pytz.timezone('US/Eastern')
            now = datetime.datetime.now(tz)
            # Run from 09:00 to 16:15
            start = now.replace(hour=9, minute=0, second=0, microsecond=0)
            end = now.replace(hour=16, minute=15, second=0, microsecond=0)
            
            if start <= now <= end and now.weekday() < 5:
                auditor.run_cycle()
                time.sleep(900) # 15 mins
            else:
                print("💤 Off-Hours. Sleeping 1h...")
                time.sleep(3600)
                
        except Exception as e:
            print(f"🔥 Crash: {e}")
            time.sleep(60)
