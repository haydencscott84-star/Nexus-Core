import os
import nexus_lock
import time, random, os, subprocess, signal, sys

# --- ROBUSTNESS: SIGNAL HANDLING ---
class GracefulKiller:
    kill_now = False
    def __init__(self, app_ref):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        self.app = app_ref

    def exit_gracefully(self, signum, frame):
        self.kill_now = True
        print("\n\n🛡️ SAFE SHUTDOWN INITIATED... (Releasing Locks & Sockets)")
        # If inside Textual app, try to stop it
        if self.app:
            try: self.app.exit()
            except: pass
        sys.exit(0) # Triggers atexit in nexus_lock

# 1. (REMOVED) HIGHLANDER PROTOCOL: Was causing suicide/fratricide crash loops.
# Relying on robust nexus_lock (flock) instead.

# 2. OPTIMIZATION: Stagger critical launch (still useful for API, less for locks now)
time.sleep(random.uniform(1.0, 2.0))

nexus_lock.enforce_singleton() # Lock acquired here. Released on sys.exit().
"""
Nexus-Powered SWING DASHBOARD (Whale Hunter - Tuned High Filter)
- FIX: Added SNAPSHOT button to Header (Restored UI)
- FIX: Strict Ticker Filter (SPY, SPX, SPXW only)
"""

import asyncio, datetime, os, json, ssl, sys, re, time
from datetime import timedelta
from collections import deque
from pathlib import Path

try:
    import zmq, zmq.asyncio, pytz, requests
    import pandas as pd
    import numpy as np
    ET = pytz.timezone('US/Eastern')
    UTC = pytz.utc
except ImportError:
    sys.exit("Missing deps. Run: pip install pyzmq pytz requests textual")

try: from nexus_config import is_market_open
except: is_market_open = lambda: True

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Log, TabbedContent, TabPane, Button
from textual.containers import Vertical, Container
from rich.text import Text

import zmq.asyncio
import argparse
import sys
from textual import work, on

# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ZMQ_PORT = 9999; ZMQ_TOPIC = "flow-alerts"
ZMQ_SELECT_PORT = 5562; ZMQ_SELECT_TOPIC = b"SELECT_SWEEP"

DEBUG_MODE = False # [FIX] Set to False for Production to save disk space
# --- STRICT TICKER LIST ---
TICKERS_TO_SHOW = ["SPY", "SPX", "SPXW"]
PREMIUM_THRESHOLDS = {"SPY": 50_000, "SPX": 500_000, "SPXW": 500_000, "DEFAULT": 999_999_999}
POLL_FAST_TICK_SECONDS = 1.0
LIVE_SWEEPS_MAXLEN = 2000 
MIN_DTE = 0; MAX_DTE = 35; SHORT_DTE_CUTOFF = 3

# --- GLOBAL STATE ---
LIVE_SWEEPS = deque(maxlen=LIVE_SWEEPS_MAXLEN)
SEEN_IDS = set()
ZMQ_STATUS = "WAITING..."
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
MARKET_LEVELS_FILE = os.path.join(SCRIPT_DIR, "market_levels.json")
MARKET_STRUCTURE = {"spy_price": 0.0, "spx_price": 0.0, "current_basis": 0.0}
FLOOR_ALERT_TRIGGERED = False

# --- SENTIMENT TRACKING ---
SENTIMENT_SCORES = {"SPY": 0, "SPX": 0}
SEEN_TRADES_SENT = set()
LAST_RESET_DATE = None
SENTIMENT_STATE_FILE = "sweeps_v3_sentiment.json"

def load_sentiment_state():
    global SENTIMENT_SCORES, SEEN_TRADES_SENT, LAST_RESET_DATE
    if os.path.exists(SENTIMENT_STATE_FILE):
        try:
            with open(SENTIMENT_STATE_FILE, 'r') as f:
                data = json.load(f)
                
            saved_date = data.get('date')
            today = get_trading_date().isoformat()
            
            if saved_date == today:
                SENTIMENT_SCORES = data.get('scores', {"SPY": 0, "SPX": 0})
                SEEN_TRADES_SENT = set(data.get('seen', []))
                LAST_RESET_DATE = today
                print(f"[SENTIMENT] Loaded V3 State: {SENTIMENT_SCORES}")
            else:
                print(f"[SENTIMENT] Stale State ({saved_date}). Resetting for {today}.")
                LAST_RESET_DATE = today
                SENTIMENT_SCORES = {"SPY": 0, "SPX": 0}
                SEEN_TRADES_SENT = set()
        except Exception as e:
            print(f"[SENTIMENT] Load Error: {e}")

def save_sentiment_state():
    try:
        data = {
            "date": get_trading_date().isoformat(),
            "scores": SENTIMENT_SCORES,
            "seen": list(SEEN_TRADES_SENT)
        }
        with open(SENTIMENT_STATE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[SENTIMENT] Save Error: {e}")

def update_cumulative_sentiment(trade):
    global SENTIMENT_SCORES, SEEN_TRADES_SENT, LAST_RESET_DATE
    
    # 1. Daily Reset
    today = get_trading_date().isoformat()
    if LAST_RESET_DATE != today:
        SEEN_TRADES_SENT.clear()
        LIVE_SWEEPS.clear() # [FIX] Clear old data on daily reset
        SENTIMENT_SCORES = {"SPY": 0, "SPX": 0}
        LAST_RESET_DATE = today
        save_sentiment_state()
        
    # 2. Dedupe
    sig = f"{trade.get('option_chain')}_{trade.get('executed_at')}_{trade.get('total_size')}"
    if sig in SEEN_TRADES_SENT: return
    
    # 3. Score
    sent = trade.get('sentiment_str', 'MID')
    prio = trade.get('priority_score', 0)
    
    score = 0
    if sent == 'BUY': score = 1
    elif sent == 'SELL': score = -1
    
    if prio >= 3: score *= 2
    
    # 4. Route to Ticker
    tkr = trade.get('ticker', '')
    if "SPX" in tkr: SENTIMENT_SCORES["SPX"] += score
    else: SENTIMENT_SCORES["SPY"] += score
    
    try:
        with open("logs/debug_sentiment.log", "a") as f:
            f.write(f"Scoring: {sig} -> Sent:{sent} Prio:{prio} Score:{score} | Total: SPY={SENTIMENT_SCORES['SPY']} SPX={SENTIMENT_SCORES['SPX']}\n")
    except: pass

    SEEN_TRADES_SENT.add(sig)
    save_sentiment_state()

class RollingStats:
    def __init__(self, window_days=30):
        self.window = datetime.timedelta(days=window_days)
        self.history = [] # List of (timestamp, value)

    def process(self, timestamp, value):
        # 1. Prune old data (Time-Based)
        cutoff = timestamp - self.window
        self.history = [x for x in self.history if x[0] > cutoff]
        
        # 2. Calculate Stats on PRIOR history (No Leakage)
        mean = 0.0
        std = 0.0
        z_score = 0.0
        
        if len(self.history) > 1:
            vals = [x[1] for x in self.history]
            mean = np.mean(vals)
            std = np.std(vals)
            if std > 0:
                z_score = (value - mean) / std
        
        # 3. Update History
        self.history.append((timestamp, value))
        
        return z_score, mean, std

import uuid

def antigravity_dump(filename, data_dictionary):
    """
    Atomically dumps data to a JSON file.
    Writes to a unique temp file first, then renames to prevent read/write collisions.
    """
    temp_file = f"{filename}.{uuid.uuid4()}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(data_dictionary, f, default=str)
        os.replace(temp_file, filename)
        
        # NEW: Print a timestamp so the user sees it is alive
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"✅ [HEARTBEAT] Wrote {filename} at {current_time}")
        
    except Exception as e:
        print(f"❌ DUMP ERROR: {e}")
        try: os.remove(temp_file)
        except: pass

# --- HELPERS ---
def get_ny_time(): return datetime.datetime.now(ET)
def get_trading_date(): 
    d = get_ny_time().date()
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d

def fmt_notional(value, show_plus=False):
    if value is None: return "N/A"
    v = abs(value)
    s = f"${v/1e9:.2f}B" if v>=1e9 else (f"${v/1e6:.1f}M" if v>=1e6 else (f"${v/1e3:.1f}K" if v>=1e3 else f"${v:.0f}"))
    return "-" + s if value < 0 else ("+" + s if show_plus else s)

def parse_option_chain(chain_symbol: str):
    try:
        match = re.search(r'(\d{6})([CP])([\d\.]+)$', chain_symbol)
        if match:
            d, t, s = match.groups()
            return f"20{d[:2]}-{d[2:4]}-{d[4:]}", "CALL" if t == 'C' else "PUT", float(s) / 1000 if len(s) == 8 and "." not in s else float(s)
        return None, None, None
    except: return None, None, None

def is_from_today(ts):
    if not ts: return False
    try:
        if isinstance(ts, (int, float)): d = datetime.datetime.fromtimestamp(ts, tz=UTC).astimezone(ET).date()
        elif isinstance(ts, str): d = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET).date()
        else: return False
        return d == get_trading_date()
    except: return False

def calculate_aggressor_score(trade):
    """
    Calculates Aggressor Score based on Price vs Bid/Ask.
    Returns: (score, weight)
    """
    price = trade.get('price', 0)
    bid = trade.get('bid', 0)
    ask = trade.get('ask', 0)
    
    # If Bid/Ask missing, fallback to sentiment
    if not bid or not ask:
        sent = trade.get('sentiment_str', 'MID')
        if sent == 'BUY': return "AGGRESSIVE BUY", 1.0
        elif sent == 'SELL': return "PASSIVE SELL", 0.1
        else: return "NEUTRAL", 0.5

    if price >= ask: return "AGGRESSIVE BUY", 1.0
    elif price <= bid: return "PASSIVE SELL", 0.1
    else: return "NEUTRAL", 0.5

def send_discord_alert(title, color, fields):
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    # Fallback to nexus_config if env var not set (Common issue)
    if not webhook_url:
        try:
            from nexus_config import DISCORD_WEBHOOK_URL
            webhook_url = DISCORD_WEBHOOK_URL
        except ImportError: pass
        
    if not webhook_url: return
    
    payload = {
        "embeds": [{
            "title": title,
            "color": color,
            "fields": fields,
            "footer": {"text": "Nexus Whale Hunter • Defensive Protocol"}
        }]
    }
    try: requests.post(webhook_url, json=payload, timeout=2)
    except: pass

def score_sweep(s_data, market, sentiment):
    score = 0; notes = []
    prem = s_data.get('total_premium', 0); dte = s_data.get('parsed_dte', -1)
    strike = s_data.get('parsed_strike', 0); otype = s_data.get('parsed_type', 'N/A')
    
    # FIX: Look-ahead bias. Use trade's underlying price if available.
    ref_price = s_data.get('underlying_price') or market.get("spy_price", 0)
    
    tkr = s_data.get('ticker', '')
    
    if dte >= 30: score += 2; notes.append("SWING")
    
    if "SPX" in tkr:
        if prem >= 5_000_000: score += 5; notes.append("GODZILLA")
        elif prem >= 2_000_000: score += 3; notes.append("WHALE")
    else:
        if prem >= 2_000_000: score += 3; notes.append("WHALE")
        elif prem >= 1_000_000: score += 1; notes.append("SIZE")

    # OTM Check using ref_price
    if ref_price > 0:
        is_otm = (otype == 'CALL' and strike > ref_price) or (otype == 'PUT' and strike < ref_price)
        if is_otm: score += 1; notes.append("OTM")

    # Opening/Closing Logic
    vol = s_data.get('total_size', 0)
    oi = s_data.get('open_interest', 0)
    if oi > 0:
        if vol > oi: 
            score += 2; notes.append("OPENING") # High Signal
        elif vol < oi:
            notes.append("AMBIGUOUS") # Dim in UI
    
    # Burst/Mega-Sweep Logic
    if s_data.get('is_burst'):
        score += 2; notes.append("BURST")
        if s_data.get('total_premium') > 1_000_000:
            score += 3; notes.append("INSTITUTIONAL URGENCY")

    # Add Z-Score context if available
    z_prem = s_data.get('z_premium', 0.0)
    if z_prem > 3.0: 
        score += 1
        m = s_data.get('mean_premium', 0)
        s = s_data.get('std_premium', 0)
        notes.append(f"Z-PREM({z_prem:.1f}σ|μ={fmt_notional(m)}|σ={fmt_notional(s)})")
    
    return score, notes

class NexusSwingEvents(App):
    BINDINGS = [("r", "reset_alert", "Reset Alert")]
    CSS = """
    Screen { layout: vertical; }
    
    /* HEADER LAYOUT FIXED to hold button */
    HeaderBox { 
        dock: top; height: 4; 
        background: $surface-darken-1; border-bottom: solid $primary; 
        layout: horizontal; align-vertical: middle; padding-left: 1; 
    }
    #header_lbl { width: 1fr; content-align: center middle; height: 100%; }
    #btn_snapshot { margin-right: 1; }

    Footer { dock: bottom; height: 1; }
    #log-container { dock: bottom; height: 8; border-top: solid $secondary-darken-2; }
    Log { height: 100%; width: 100%; background: $surface; color: $text; overflow-y: scroll; }
    #main-view { height: 1fr; width: 100%; }
    TabbedContent { height: 100%; }
    ContentSwitcher { height: 100%; }
    TabPane { height: 100%; padding: 0; }
    SweepTable { height: 100%; width: 100%; }
    """

    _alert_session = requests.Session()
    zmq_ctx = zmq.asyncio.Context()
    select_sock = None
    last_snapshot_hour = -1

    # Rolling Stats for Stationarity (Time-Based, 30 Days)
    stats_premium = RollingStats(window_days=30)
    stats_vol = RollingStats(window_days=30)

    class HeaderBox(Container):
        def compose(self) -> ComposeResult:
            yield Static(id="header_lbl")
            yield Button("SNAPSHOT", id="btn_snapshot", variant="warning")
            
        def on_mount(self): self.set_interval(1.0, self.update_header)
        
        def update_header(self):
            now = get_ny_time()
            stats = {
                "SPY": {"bull": 0.0, "bear": 0.0}, "SPX": {"bull": 0.0, "bear": 0.0},
                "D0":  {"bull": 0.0, "bear": 0.0}, "D1":  {"bull": 0.0, "bear": 0.0},
                "TOTAL": {"bull": 0.0, "bear": 0.0}
            }
            
            # For State Dumping
            bull_list = []
            bear_list = []
            total_prem_dump = 0.0

            # Calculate stats only for TODAY'S data
            cnt_total = 0
            cnt_today = 0
            for s in list(LIVE_SWEEPS):
                cnt_total += 1
                if not is_from_today(s.get('executed_at')): continue
                cnt_today += 1

                prem = s.get('total_premium', 0); sent = s.get('sentiment_str', 'MID')
                otype = s.get('parsed_type', 'N/A'); tkr = s.get('ticker', '')
                dte = s.get('parsed_dte', -1)
                
                total_prem_dump += prem

                # Aggressor Weighting
                aggressor_tag, weight = calculate_aggressor_score(s)
                weighted_prem = prem * weight
                
                bkt = "bull" if (sent == "BUY" and otype == "CALL") or (sent == "SELL" and otype == "PUT") else "bear"
                
                if bkt == "bull": bull_list.append(s)
                else: bear_list.append(s)

                k = "SPX" if "SPX" in tkr else "SPY"
                stats[k][bkt] += weighted_prem
                if dte <= SHORT_DTE_CUTOFF: stats['D0'][bkt] += weighted_prem
                else: stats['D1'][bkt] += weighted_prem
                stats['TOTAL'][bkt] += weighted_prem

            # --- DELTA AGGREGATION [PATCH] ---
            # Calculate Net Delta Exposure (Delta * Size * 100)
            net_delta_d0 = 0.0
            net_delta_d1 = 0.0
            
            for s in list(LIVE_SWEEPS):
                if not is_from_today(s.get('executed_at')): continue
                
                # Delta is per contract (-1.0 to 1.0). 
                # Contracts = total_size
                # Multiplier = 100
                d = s.get('delta', 0.0)
                sz = s.get('total_size', 0)
                dte = s.get('parsed_dte', -1)
                
                # Standard Option Delta Exposure
                delta_exp = d * sz * 100
                
                if dte <= SHORT_DTE_CUTOFF: net_delta_d0 += delta_exp
                else: net_delta_d1 += delta_exp
            # ---------------------------------

            c = lambda v: "green" if v>=0 else "red"
            spy_n = stats['SPY']['bull'] - stats['SPY']['bear']
            spx_n = stats['SPX']['bull'] - stats['SPX']['bear']
            d0_n = stats['D0']['bull'] - stats['D0']['bear']
            d1_n = stats['D1']['bull'] - stats['D1']['bear']
            tot_n = stats['TOTAL']['bull'] - stats['TOTAL']['bear']
            
            basis = MARKET_STRUCTURE.get('current_basis', 0.0)
            basis_str = f"[bold white]Spread:[/] [{c(basis)}]{basis:+.2f}[/]"
            
            # Floor Guard Status
            floor_status = "[bold red blink]⚠️ FLOOR RISING [SPY, PUT, (<55dte), (>675), (>$1m)][/]" if FLOOR_ALERT_TRIGGERED else "[bold green]🛡️ FLOOR GUARD [SPY, PUT, (<55dte), (>675), (>$1m)][/]"
            
            c_spy = "green" if SENTIMENT_SCORES["SPY"] >= 0 else "red"
            c_spx = "green" if SENTIMENT_SCORES["SPX"] >= 0 else "red"
            
            iv_disp = MARKET_STRUCTURE.get('iv_30d', 0)
            
            spx_spot = MARKET_STRUCTURE.get('spx_price', 0)
            spy_spot = MARKET_STRUCTURE.get('spy_price', 0)
            range_str = ""
            
            if iv_disp > 0:
                iv_valid = True
                # SPX 30D
                if spx_spot > 0:
                    m_x = spx_spot * iv_disp * np.sqrt(30/365)
                    range_str += f" [bold cyan]SPX:{spx_spot-m_x:.0f}-{spx_spot+m_x:.0f}[/]"
                # SPY 30D
                if spy_spot > 0:
                    m_y = spy_spot * iv_disp * np.sqrt(30/365)
                    range_str += f" [bold cyan]SPY:{spy_spot-m_y:.1f}-{spy_spot+m_y:.1f}[/]"

            l1 = f" [bold]NEXUS[/] | {now.strftime('%H:%M:%S')} | {basis_str} | {floor_status} | IV:{iv_disp*100:.1f}%{range_str} | [{c_spy}]SPY:{SENTIMENT_SCORES['SPY']}[/] [{c_spx}]SPX:{SENTIMENT_SCORES['SPX']}[/]"
            l2 = (f" SPY Net: [{c(spy_n)}]{fmt_notional(spy_n,True)}[/] | SPX Net: [{c(spx_n)}]{fmt_notional(spx_n,True)}[/]  [dim]||[/]  "
                  f"0-3D: [{c(d0_n)}]{fmt_notional(d0_n,True)}[/] | 3+D: [{c(d1_n)}]{fmt_notional(d1_n,True)}[/]  [dim]||[/]  "
                  f"TOT: [{c(tot_n)}]{fmt_notional(tot_n,True)}[/]")
            
            self.query_one("#header_lbl", Static).update(Text.from_markup(f"{l1}\n{l2}"))
            
            # DEBUG UI
            if DEBUG_MODE and cnt_total > 0:
                try:
                    with open("logs/debug_ui.log", "a") as f:
                         f.write(f"UI Update: Total={cnt_total} Today={cnt_today} Stats={len(bull_list)}/{len(bear_list)} NetSpX={spx_n}\n")
                except: pass

            # --- ANTIGRAVITY STATE DUMP ---
            current_state = {
                "total_premium": total_prem_dump,
                "bullish_flow_list": bull_list,
                "bearish_flow_list": bear_list,
                "sentiment_scores": SENTIMENT_SCORES,
                "metrics": {
                    "3dte_plus_net_delta": net_delta_d1,
                    "0dte_net_delta": net_delta_d0
                },
                "timestamp": time.time()
            }
            antigravity_dump("nexus_sweeps_v2.json", current_state)

    class SweepTable(DataTable):
        sweeps_on_display = []
        # REMOVED: last_data_signature optimization (It was causing UI freezes)

        def __init__(self, dte_mode="ALL", **kwargs): super().__init__(**kwargs); self.dte_mode = dte_mode
        def on_mount(self):
            self.add_columns("Prem", "Age", "Time", "Tkr", "Exp", "DTE", "Strike", "Type", "Side", "Details", "Notes")
            self.cursor_type = "row"; self.set_interval(1.0, self.update_table)
        
        def update_table(self):
            if not LIVE_SWEEPS: return
            
            # FILTER: Today Only + DTE
            to_show = [s for s in list(LIVE_SWEEPS) if is_from_today(s.get('executed_at'))]
            
            # DEBUG RENDER
            if len(LIVE_SWEEPS) > 0 and self.dte_mode == "ALL": 
                 if len(to_show) == 0: self.app.log_msg(f"Render Fail: LIVE={len(LIVE_SWEEPS)} but Today={len(to_show)}")
                 # else: self.app.log_msg(f"Render OK: Showing {len(to_show)} items")
            
            if self.dte_mode == "SHORT": to_show = [s for s in to_show if s.get('parsed_dte',-1) <= SHORT_DTE_CUTOFF]
            elif self.dte_mode == "LONG": to_show = [s for s in to_show if s.get('parsed_dte',-1) > SHORT_DTE_CUTOFF]
            # else: ALL (Default)
            
            to_show.sort(key=lambda s: float(s.get('total_premium', 0)), reverse=True)
            
            # --- FIX: Prevent Table Snap on Redundant Updates ---
            if not hasattr(self, 'sweeps_on_display'): self.sweeps_on_display = []
            
            current_uids = [s.get('uid') for s in self.sweeps_on_display]
            new_uids = [s.get('uid') for s in to_show]
            
            if current_uids == new_uids: return # NO CHANGE -> NO RENDER
            
            self.sweeps_on_display = to_show
            saved_row = self.cursor_coordinate.row
            
            # Optimization: Only clear if we actually have data to show, otherwise keep existing state or clear empty
            self.clear()
            
            for i, s in enumerate(to_show):
                ts = s.get('executed_at') or 0
                tm = datetime.datetime.fromtimestamp(ts, tz=ET).strftime("%H:%M:%S") if ts else "00:00:00"
                
                otype = s.get('parsed_type', 'N/A'); ost = "green" if otype=='CALL' else "red"
                sent = s.get('sentiment_str', 'MID'); sst = "green" if sent=='BUY' else ("red" if sent=='SELL' else "white")
                stk = s.get('parsed_strike', 0)
                basis = MARKET_STRUCTURE.get('current_basis', 0.0)
                
                if "SPX" in s.get('ticker', '') and abs(basis) > 0.1: stk_s = f"${stk:,.0f} ({(stk-basis)/10:.2f})"
                else: stk_s = f"${stk:,.2f}".replace(".00", "")
                
                prem = s.get('total_premium', 0)
                # --- NEW AGE FORMATTER ---
                if ts > 0:
                    diff = int(time.time() - ts)
                    if diff < 60: 
                        age = f"{diff}s"
                    elif diff < 3600: 
                        age = f"{diff // 60}m"
                    else: 
                        age = f"{diff // 3600}h {(diff % 3600) // 60}m"
                else: 
                    age = "?"
                # -------------------------

                # --- PRIORITY STYLING (MINIMALIST) ---
                sc = s.get('priority_score', 0)
                if sc >= 5: sc_render = Text(f"{sc}", style="bold red")
                elif sc >= 3: sc_render = Text(f"{sc}", style="bold yellow")
                elif sc >= 1: sc_render = Text(f"{sc}", style="bold blue")
                else: sc_render = Text(f"{sc}", style="dim")

                # --- NOTES STYLING (MINIMALIST - TEXT ONLY) ---
                note_badges = []
                raw_notes = s.get('priority_notes', '').split(', ')
                for n in raw_notes:
                    if not n: continue
                    if "OTM" in n: note_badges.append(f"[bold green]{n}[/]")
                    elif "SWING" in n: note_badges.append(f"[bold blue]{n}[/]")
                    elif "SIZE" in n: note_badges.append(f"[bold yellow]{n}[/]")
                    elif "WHALE" in n: note_badges.append(f"[bold yellow]{n}[/]")
                    elif "GODZILLA" in n: note_badges.append(f"[bold red]{n}[/]")
                    elif "Z-PREM" in n: note_badges.append(f"[bold magenta]{n}[/]")
                    elif "OPENING" in n: note_badges.append(f"[bold gold1]{n}[/]")
                    elif "INSTITUTIONAL URGENCY" in n: note_badges.append(f"[bold red blink]{n}[/]")
                    elif "BURST" in n: note_badges.append(f"[bold orange1]{n}[/]")
                    else: note_badges.append(f"[dim]{n}[/]")
                notes_render = Text.from_markup(" ".join(note_badges))
                
                # Dim row if Ambiguous
                row_style = "dim" if "AMBIGUOUS" in raw_notes else ""

                # [FIX] Use stable UID as key instead of index to prevent rendering glitches
                row_key = s.get('uid', str(i))
                try:
                    self.add_row(Text(fmt_notional(prem), style="bold " + sst), 
                                 Text(age, style="dim"), tm, s.get('ticker'), s.get('parsed_expiry'), str(s.get('parsed_dte')),
                                 stk_s, Text(otype, style=ost), Text(sent, style=sst),
                                 f"{s.get('total_size')} @ ${s.get('price')}", notes_render, key=row_key)
                except Exception: pass # Ignore duplicates if they slip through
                
                if row_style == "dim":
                    # Textual DataTable doesn't support row styling easily this way, 
                    # but we can style individual cells or just rely on the notes being dim.
                    # For now, the "AMBIGUOUS" tag is dim, which helps.
                    pass
            
            if saved_row > 0 and saved_row < self.row_count: self.move_cursor(row=saved_row, animate=False)

    def action_reset_alert(self):
        global FLOOR_ALERT_TRIGGERED
        FLOOR_ALERT_TRIGGERED = False
        self.notify("Floor Guard Reset")

    def compose(self) -> ComposeResult:
        yield self.HeaderBox()
        with Container(id="main-view"):
            with TabbedContent(initial="all"):
                with TabPane("ALL FLOW", id="all"): yield self.SweepTable(id="t_all", dte_mode="ALL")
                with TabPane(f"0-{SHORT_DTE_CUTOFF} DTE", id="d0"): yield self.SweepTable(id="t0", dte_mode="SHORT")
                with TabPane(f"{SHORT_DTE_CUTOFF}+ DTE", id="d1"): yield self.SweepTable(id="t1", dte_mode="LONG")
        with Container(id="log-container"): yield Log(id="app-log")
        yield Footer()

    async def on_mount(self):
        self.log_msg("Init Whale Hunter (V2 UI Fixed)...")
        # [ROBUSTNESS] Register Signal Handler
        self.killer = GracefulKiller(self)
        
        self.sync_update_market_structure_once() # [FIX] Force Load State BEFORE Fetching Data
        self.update_market_structure()
        
        # Load Sentiment Persistence
        load_sentiment_state()
        
        # HEADLESS MODE: Fetch, Dump, Loop
        if getattr(self, "HEADLESS", False):
            self.log_msg("HEADLESS MODE: Starting Loop...")
            while True:
                self.log_msg("HEADLESS: Fetching Backfill...")
                await self.fetch_backfill_logic()
                self.log_msg("HEADLESS: Dumping State...")
                self.dump_state_to_json()
                self.log_msg("HEADLESS: Sleeping 5m...")
                await asyncio.sleep(300) # 5 minutes
            return

        self.fetch_backfill()
        self.stream_zmq_data()
        
        try:
            self.select_sock = self.zmq_ctx.socket(zmq.PUB)
            self.select_sock.bind(f"tcp://127.0.0.1:{ZMQ_SELECT_PORT}")
        except Exception as e: self.log_msg(f"Select Sock Fail: {e}")

        # AUTO SNAPSHOT TIMER (Every 60s check)
        self.set_interval(60.0, self.check_auto_snapshot)

    def dump_state_to_json(self):
        # Extracted from update_header
        bull_list = []
        bear_list = []
        total_prem_dump = 0.0
        
        # [FIX] Recalculate Scores from scratch based on filtered list (Daily Reset Guarantee)
        fresh_scores = {"SPY": 0, "SPX": 0}

        for s in list(LIVE_SWEEPS):
            if not is_from_today(s.get('executed_at')): continue
            prem = s.get('total_premium', 0); sent = s.get('sentiment_str', 'MID')
            otype = s.get('parsed_type', 'N/A')
            total_prem_dump += prem
            bkt = "bull" if (sent == "BUY" and otype == "CALL") or (sent == "SELL" and otype == "PUT") else "bear"
            if bkt == "bull": bull_list.append(s)
            else: bear_list.append(s)
            
            # Recalc Logic
            tkr = "SPY" if "SPY" in s.get('option_chain', '') else ("SPX" if "SPX" in s.get('option_chain', '') else None)
            if tkr:
                sc = 1 if sent == "BUY" else (-1 if sent == "SELL" else 0)
                if s.get('priority_score', 0) >= 3: sc *= 2
                fresh_scores[tkr] += sc

        current_state = {
            "total_premium": total_prem_dump,
            "bullish_flow_list": bull_list,
            "bearish_flow_list": bear_list,
            "sentiment_scores": fresh_scores, # [FIX] Use fresh calc
            "timestamp": time.time()
        }
        antigravity_dump("nexus_sweeps_v2.json", current_state)

    def check_auto_snapshot(self):
        now = get_ny_time()
        target_hours = [10, 14, 18]
        if now.hour in target_hours and now.minute < 5:
            if self.last_snapshot_hour != now.hour:
                self.on_manual_snapshot() # Reuse the manual logic
                self.last_snapshot_hour = now.hour
                self.log_msg(f"Auto-Snapshot Triggered ({now.strftime('%H:%M')})")
        elif now.hour not in target_hours:
            self.last_snapshot_hour = -1

    # --- BUTTON HANDLER ---
    @on(Button.Pressed, "#btn_snapshot")
    def on_manual_snapshot(self):
        if not LIVE_SWEEPS: return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_dir = Path("snapshots_sweeps"); save_dir.mkdir(exist_ok=True)
        csv_filename = save_dir / f"{timestamp}_sweeps_flow_v2.csv"
        
        try:
            # Filter for TODAY ONLY
            valid_rows = [s for s in list(LIVE_SWEEPS) if is_from_today(s.get('executed_at'))]
            if not valid_rows: return

            df = pd.DataFrame(valid_rows)
            cols = ['ticker', 'parsed_expiry', 'parsed_dte', 'parsed_strike', 'parsed_type', 'sentiment_str', 'total_premium', 'priority_score', 'priority_notes', 'price', 'total_size', 'delta', 'gamma']
            
            # Safe column filter
            existing = [c for c in cols if c in df.columns]
            if existing: df = df[existing]
            
            df.to_csv(csv_filename, index=False)
            print(f"[PATCHED] Added 'delta' column to {csv_filename} output.")
            self.notify(f"Snapshot Saved: {timestamp}")
            self.log_msg(f"Saved Snapshot: {csv_filename}")
        except Exception as e: 
            self.log_msg(f"Snapshot Fail: {e}")
            self.notify(f"Error saving snapshot", severity="error")

    @work()
    async def fetch_backfill(self):
        while True:
            await self.fetch_backfill_logic()
            self.log_msg("Backfill Complete. Refreshing UI...")
            self.query_one("SweepTable").update_table() # Force TUI refresh
            await asyncio.sleep(30) # Refresh every 30s for now to ensure data populates

    async def fetch_backfill_logic(self):
        if not is_market_open(): return

        url = "https://api.unusualwhales.com/api/option-trades/flow-alerts"
        headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        loop = asyncio.get_event_loop()
        today_str = get_trading_date().strftime("%Y-%m-%d") # FORCE TODAY (Active Session)

        for t in TICKERS_TO_SHOW:
            try:
                th = PREMIUM_THRESHOLDS.get(t, 250_000)
                p = {'ticker_symbol': t, 'limit': 500, 'min_premium': th, 'min_dte': MIN_DTE, 'max_dte': MAX_DTE, 'date': today_str}
                r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, params=p, timeout=5))
                try:
                    with open("logs/sweeps_api_debug.log", "a") as f:
                        f.write(f"[{datetime.datetime.now()}] Ticker: {t} Status: {r.status_code} Items: {len(r.json().get('data', []))}\n")
                except: pass

                if r.status_code == 200:
                    for i in reversed(r.json().get('data', [])):
                        self.process_row(i, is_history=True)
                
                # OPTIMIZATION: Stagger API calls to prevent rate limits
                await asyncio.sleep(1.5)
            except Exception as e: self.log_msg(f"Backfill Err {t}: {e}")

    @work()
    async def stream_zmq_data(self):
        global ZMQ_STATUS
        s = self.zmq_ctx.socket(zmq.SUB)
        try:
            # FIX 1: Subscribe to ALL topics (""), not just "flow-alerts"
            # This allows "option_trades:SPY" and "option_trades:SPX" to enter the script.
            s.connect(f"tcp://127.0.0.1:{ZMQ_PORT}")
            s.setsockopt_string(zmq.SUBSCRIBE, "") 
            
            ZMQ_STATUS = "CONNECTED"
            self.log_msg("ZMQ Connected (Listening to Raw + Alerts)")
            
            while True:
                try:
                    if not is_market_open():
                        await asyncio.sleep(60)
                        continue

                    # ZMQ sends [topic, json_payload]
                    msg = await s.recv_multipart()
                    if len(msg) < 2 or not msg[1]: continue # Validate Payload

                    try:
                        # We don't filter by topic here because your 'process_row' 
                        # already filters by Ticker (SPY/SPX).
                        payload = json.loads(msg[1].decode('utf-8'))
                        self.process_row(payload, is_history=False)
                    except json.JSONDecodeError as e:
                        if DEBUG_MODE: self.log_msg(f"JSON Err: {e}")
                    except Exception as e:
                        if DEBUG_MODE: self.log_msg(f"Process Err: {e}")

                except Exception as e: 
                    self.log_msg(f"Stream Err: {e}")
        except Exception as e: 
            ZMQ_STATUS = "ERROR"
            self.log_msg(f"ZMQ Connect Err: {e}")

    def process_row(self, i, is_history=False):
        try:
            with open("logs/debug_raw_stream.jsonl", "a") as f: f.write(json.dumps(i) + "\n")

            tkr = i.get('ticker') or i.get('underlying_symbol')
            if tkr not in TICKERS_TO_SHOW: 
                return

            # FIX 2: Handle "timestamp" (Raw Trades) vs "executed_at" (Alerts)
            ts = i.get('executed_at') or i.get('created_at') or i.get('timestamp') or i.get('date')
            if not ts: return

            ts_val = 0.0
            if isinstance(ts, str):
                try: ts_val = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                except: return
            else:
                ts_val = float(ts)

            # FIX 3: Detect Milliseconds (Common in raw feeds)
            if ts_val > 100_000_000_000: ts_val = ts_val / 1000.0

            # Filter for TODAY
            if not is_from_today(ts_val): 
                if DEBUG_MODE: self.log_msg(f"Date Reject: {ts_val} vs {get_trading_date()}")
                return
            
            # FIX 4: Normalize Keys (Raw Trades use 'premium', Alerts use 'total_premium')
            prem = float(i.get('total_premium') or i.get('premium') or 0)
            
            # [CRITICAL FIX] Fallback calculation if key missing
            if prem == 0:
                sz = float(i.get('total_size') or i.get('size') or 0)
                pr = float(i.get('price') or i.get('p') or 0)
                prem = sz * pr * 100

            # TUI DEBUG (Now safe to use prem)
            if DEBUG_MODE: self.log_msg(f"Processing: {tkr} Prem: {prem}")

            # FILTER: Minimum Premium Check (Restored)
            if prem < PREMIUM_THRESHOLDS.get(tkr, 250_000): 
                 # Optional: log rejects to debug file if needed, but keeping it clean for now
                 return
            
            size = int(i.get('total_size') or i.get('size') or i.get('volume') or 0)
            price = float(i.get('price') or i.get('p') or 0)
            
            # Construct standard dictionary for your Logic
            d = {
                'ticker': tkr, 'total_premium': prem, 
                'option_chain': i.get('option_chain') or i.get('symbol'),
                'executed_at': ts_val,
                'total_size': size, 
                'price': price,
                'bid': float(i.get('bid') or i.get('bid_price') or 0),
                'ask': float(i.get('ask') or i.get('ask_price') or 0),
                'open_interest': int(i.get('open_interest') or 0),
                'underlying_price': float(i.get('underlying_price') or i.get('stock_price') or 0),
                # Calculate side volume if missing (Raw trades often miss this, so we estimate)
                'total_ask_side_prem': float(i.get('total_ask_side_prem') or i.get('ask_side_volume', 0) * price * 100 or 0),
                'total_bid_side_prem': float(i.get('total_bid_side_prem') or i.get('bid_side_volume', 0) * price * 100 or 0),
                # [PATCHED] Added 'delta' capture
                'delta': float(i.get('greeks', {}).get('delta') or i.get('delta') or 0.0),
                'gamma': float(i.get('greeks', {}).get('gamma') or i.get('gamma') or 0.0)
            }
            

            
            chain = d.get('option_chain'); exp, otype, stk = parse_option_chain(chain)
            if not all([exp, otype, stk]): return
            dte = (datetime.date.fromisoformat(exp) - get_trading_date()).days
            if dte > MAX_DTE: return # Filter out > MAX_DTE (User req: <=35)

            # FILTER: IV Range Check
            # Rejects trades where Strike is outside the 30-Day Implied Move
            iv_30 = MARKET_STRUCTURE.get('iv_30d', 0)
            curr_spot = 0
            if "SPX" in tkr: curr_spot = MARKET_STRUCTURE.get('spx_price', 0)
            elif "SPY" in tkr: curr_spot = MARKET_STRUCTURE.get('spy_price', 0)
            
            if iv_30 > 0 and curr_spot > 0:
                imp_move = curr_spot * iv_30 * np.sqrt(30/365)
                low_bound = curr_spot - imp_move
                high_bound = curr_spot + imp_move
                if stk < low_bound or stk > high_bound: 
                    # if DEBUG_MODE: self.log_msg(f"IV Reject: {tkr} ${stk} outside {low_bound:.0f}-{high_bound:.0f}")
                    return
            d['parsed_dte'] = dte
            d['parsed_expiry'] = exp
            d['parsed_type'] = otype
            d['parsed_strike'] = stk
            # Generate UID
            uid = f"{d['option_chain']}_{d['total_premium']}_{d['executed_at']}"
            d['uid'] = uid # For table key


            d.update({'parsed_expiry':exp, 'parsed_type':otype, 'parsed_strike':stk, 'parsed_dte':dte})

            # --- DEFENSIVE ALERT: RISING FLOOR ---
            # Logic: Are Whales selling Puts ABOVE our profit target ($675)?
            # If yes, they are front-running the drop.
            # FIX: Check Uniqueness & Live Status
            # uid is already set below at line 920, but we need it here for the check if we want
            # Actually, line 920 sets 'uid' again. The deleted block defined 'uid' too.
            # We can rely on uid being generated later or generate it now. 
            # Let's generate it here for logic consistency.
            temp_uid = f"{d['option_chain']}_{d['total_premium']}_{d['executed_at']}"
            
            if (not is_history and temp_uid not in SEEN_IDS and
                d['ticker'] == 'SPY' and 
                d['parsed_type'] == 'PUT' and 
                d['sentiment_str'] == 'SELL' and
                d['parsed_dte'] < 55 and          # Covers your 49 DTE timeframe
                d['parsed_strike'] >= 675 and     # The "Danger Zone" for your short
                d['total_premium'] >= 1_000_000): # Whale Conviction
                
                global FLOOR_ALERT_TRIGGERED
                FLOOR_ALERT_TRIGGERED = True
                
                send_discord_alert(
                    title="⚠️ FLOOR RISING ALERT",
                    color=0xFFA500, # Orange Warning
                    fields=[
                        {"name": "Strike", "value": f"${d['parsed_strike']:.2f}"},
                        {"name": "Premium", "value": fmt_notional(d['total_premium'])},
                        {"name": "Expiry", "value": f"{d['parsed_expiry']} ({d['parsed_dte']}d)"},
                        {"name": "Significance", "value": "Whales Selling Puts ABOVE target. Support is moving up."}
                    ]
                )

            
            # [FILTER] Max DTE (User Request) - Redundant but safe
            if dte > MAX_DTE: return

            # [FILTER] Expected Move (IV Based)
            # Formula: Spot * IV * sqrt(DTE/365)
            # NOTE: IV is decimal (0.12 = 12%). do NOT divide by 100.
            iv_30 = MARKET_STRUCTURE.get('iv_30d', 0)
            underlying = d.get('underlying_price', 0)
            
            # [FIX] Fallback to Global Spot if invalid in trade data
            if underlying <= 0:
                if "SPX" in tkr: underlying = MARKET_STRUCTURE.get('spx_price', 0)
                elif "SPY" in tkr: underlying = MARKET_STRUCTURE.get('spy_price', 0)

            if underlying > 0 and iv_30 > 0:
                iv = iv_30 
                # Use DTE=1 minimum to prevent zero range on 0-DTE
                time_decay = np.sqrt(max(dte, 1) / 365.0)
                exp_move = underlying * iv * time_decay
                
                lower = underlying - exp_move
                upper = underlying + exp_move
                
                # Check if Strike is WITHIN range
                if stk < lower or stk > upper: return
            
            # --- BURST DETECTION (Mega-Sweep) ---
            # Check if this trade matches the previous trade in LIVE_SWEEPS within 500ms
            if LIVE_SWEEPS:
                last_trade = LIVE_SWEEPS[0]
                if (last_trade['option_chain'] == d['option_chain'] and 
                    abs(d['executed_at'] - last_trade['executed_at']) < 0.5):
                    
                    # MERGE into last trade
                    last_trade['total_size'] += d['total_size']
                    last_trade['total_premium'] += d['total_premium']
                    last_trade['is_burst'] = True
                    
                    # Re-score the merged trade
                    # Note: We don't re-add to LIVE_SWEEPS, just update in place
                    # But we need to update stats? 
                    # Actually, for Z-score, we already processed the individual components?
                    # No, we haven't processed this new 'd' yet.
                    # If we merge, we should probably NOT process 'd' as a separate event for Z-score 
                    # to avoid double counting if we were strictly time-series, 
                    # but for "Burst" visualization, merging is key.
                    
                    # Let's just update the display values of the last trade
                    # And re-run scoring to catch "INSTITUTIONAL URGENCY"
                    sc, n = score_sweep(last_trade, MARKET_STRUCTURE, last_trade['sentiment_str'])
                    last_trade['priority_score'] = sc
                    last_trade['priority_notes'] = ", ".join(n)
                    return # Skip adding 'd' as a new row

            sent = "BUY" if d['total_ask_side_prem'] > d['total_bid_side_prem'] else ("SELL" if d['total_bid_side_prem'] > d['total_ask_side_prem'] else "MID")
            d['sentiment_str'] = sent
            
            if d.get('underlying_price') > 0:
                if "SPY" in tkr: MARKET_STRUCTURE['spy_price'] = d['underlying_price']
                elif "SPX" in tkr: MARKET_STRUCTURE['spx_price'] = d['underlying_price']

            # Update Rolling Stats & Calculate Z-Score (Leakage Fixed)
            ts_dt = datetime.datetime.fromtimestamp(d['executed_at'], tz=ET)
            d['z_premium'], d['mean_premium'], d['std_premium'] = self.stats_premium.process(ts_dt, d['total_premium'])
            d['z_vol'], d['mean_vol'], d['std_vol'] = self.stats_vol.process(ts_dt, d['total_size'])

            sc, n = score_sweep(d, MARKET_STRUCTURE, sent)
            d['priority_score'] = sc; d['priority_notes'] = ", ".join(n)
            
            uid = f"{d['option_chain']}_{d['total_premium']}_{d['executed_at']}"
            d['uid'] = uid # [FIX] Store for stable table keys
            
            # [CRITICAL FIX] Prevent Duplicates (Backfill vs Live overlap)
            if uid in SEEN_IDS: 
                # Silent is okay here
                return
            SEEN_IDS.add(uid)
            
            # Update Global Sentiment
            update_cumulative_sentiment(d)
            
            LIVE_SWEEPS.appendleft(d)
                
            # OUTPUT FOR SHADOW BOT (Log File)
            # print(json.dumps(d, default=str), flush=True) # REMOVED: TUI swallows stdout
            # OUTPUT FOR SHADOW BOT (Log File)
            try:
                log_dir = Path("logs"); log_dir.mkdir(exist_ok=True)
                with open(log_dir / "sweeps_v2.log", "a") as f:
                    f.write(json.dumps(d, default=str) + "\n")
            except: pass
            
        except Exception as e: 
             if DEBUG_MODE: self.log_msg(f"Process Err: {e}")

    def sync_update_market_structure_once(self):
        """Synchronous update for startup to prevent race conditions."""
        try:
            spy = MARKET_STRUCTURE.get('spy_price', 0); spx = MARKET_STRUCTURE.get('spx_price', 0)
            if spy > 0 and spx > 0: MARKET_STRUCTURE['current_basis'] = spx - (spy * 10)
            
            # [OPTIMIZATION] Only log change or error
            if os.path.exists(MARKET_LEVELS_FILE):
                with open(MARKET_LEVELS_FILE, 'r') as f: MARKET_STRUCTURE.update(json.load(f))
            
            # self.log_msg(f"Init Sync State: IV={MARKET_STRUCTURE.get('iv_30d', 'N/A')}")
        except Exception as e: self.log_msg(f"Init Sync Err: {e}")

    @work(thread=True)
    def update_market_structure(self):
        global MARKET_STRUCTURE
        while True:
            if not is_market_open():
                time.sleep(60)
                continue

            try:
                self.sync_update_market_structure_once()
            except: pass
            time.sleep(5) # [FIX] Increase sleep to 5s to reduce IO pressure

    def log_msg(self, m): 
        ts = datetime.datetime.now(ET).strftime('%H:%M:%S')
        self.query_one(Log).write(f"[{ts}] {m}")
        try:
            with open("logs/app_debug.log", "a") as f: f.write(f"[{ts}] {m}\n")
        except: pass
    
    @on(DataTable.RowSelected)
    def on_sel(self, e: DataTable.RowSelected):
        if not self.select_sock: return
        try:
            t_id = e.data_table.id; tbl = self.query_one(f"#{t_id}", self.SweepTable)
            s = tbl.sweeps_on_display[int(e.row_key.value)]
            conf = "🟢 BULL" if s['sentiment_str']=="BUY" else ("🔴 BEAR" if s['sentiment_str']=="SELL" else "⚪ MID")
            be = s['parsed_strike'] + s['price'] if s['parsed_type']=='CALL' else s['parsed_strike'] - s['price']
            m = {'symbol': s['option_chain'], 'exp': s['parsed_expiry'], 'dte': s['parsed_dte'],
                'stk': s['parsed_strike'], 'type': s['parsed_type'], 'prem': s['total_premium'],
                'mkt': s['price'], 'vol': s['total_size'], 'conf': conf, 'is_ml': False,
                'oi': 0, 'voi_ratio': 0, 'pc_ratio_vol': 0, 'pc_ratio_oi': 0, 'theo': s['price'],
                'edge': 0, 'win': -1, 'be': be}
            self.select_sock.send_multipart([ZMQ_SELECT_TOPIC, json.dumps(m).encode('utf-8')])
            self.notify(f"Sent {m['symbol']}")
        except Exception as e: self.log_msg(f"Sel Err: {e}")

if __name__ == "__main__": 
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (fetch, dump, exit)")
    args = parser.parse_args()
    DEBUG_MODE = args.debug
    
    if args.headless:
        print("[*] HEADLESS MODE: Bypassing TUI.")
        app = NexusSwingEvents()
        # Manually set up loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # We need to minimally init the app logic or just call the logic
        # Since logic is bound to 'self', we can instantiate app but NOT run it.
        # But app.on_mount has the setup.
        # Let's verify if we can just call on_mount?
        # Textual might complain. Better to extract logic.
        
        # EXTRACTED LOOP:
        async def headless_runner():
            print("[*] Init Headless Runner...")
            # Init Logic (from on_mount)
            app.update_market_structure()
            # ZMQ
            app.zmq_ctx = zmq.asyncio.Context()
            app.select_sock = app.zmq_ctx.socket(zmq.PUB)
            try: app.select_sock.bind(f"tcp://127.0.0.1:{ZMQ_SELECT_PORT}")
            except: pass
            
            # Start ZMQ Streamer task
            asyncio.create_task(app.stream_zmq_data())
            
            print("[*] Starting Headless Loop...")
            while True:
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] HEADLESS: Fetching Backfill...")
                await app.fetch_backfill_logic()
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] HEADLESS: Dumping State...")
                app.dump_state_to_json()
                print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] HEADLESS: Sleeping 5m...")
                await asyncio.sleep(300)

        loop.run_until_complete(headless_runner())
        
    else:
        app = NexusSwingEvents()
        app.HEADLESS = args.headless
        app.run()