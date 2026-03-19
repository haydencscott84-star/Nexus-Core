import os
# FILE: nexus_sweeps_tui_v1.py
import nexus_lock
nexus_lock.enforce_singleton()
"""
Nexus-Powered Live Sweeps Dashboard (V1.16 - SNAPBACK FIX)
- PORT: 5561 (Runs alongside V2)
- FIX: "Snapback" on scroll fixed using call_after_refresh
- FIX: Added logic to prevent cursor stealing focus on updates
"""

import asyncio, datetime, os, json, ssl, sys, re, time
from collections import deque
from pathlib import Path 

try:
    import zmq, zmq.asyncio, pytz, requests
    import pandas as pd
    import numpy as np
    ET = pytz.timezone('US/Eastern')
    UTC = pytz.utc
except ImportError:
    sys.exit("Missing deps. Run: pip install pyzmq pytz requests textual pandas numpy")

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Log, TabbedContent, TabPane, Button
from textual.containers import Vertical, Container
from rich.text import Text
from textual import work, on

import zmq.asyncio
import argparse
import sys

# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ZMQ_PORT = 9999; ZMQ_TOPIC = "flow-alerts"
ZMQ_SELECT_PORT = 5561; ZMQ_SELECT_TOPIC = b"SELECT_SWEEP" 

DEBUG_MODE = False 

TICKERS_TO_SHOW = ["SPY", "SPX", "SPXW"]
PREMIUM_THRESHOLDS = {"SPY": 25000, "SPX": 50000, "SPXW": 50000, "DEFAULT": 25000}
POLL_FAST_TICK_SECONDS = 0.5
LIVE_SWEEPS_MAXLEN = 1000
MIN_DTE = 0; MAX_DTE = 45; SHORT_DTE_CUTOFF = 3

# --- GLOBAL STATE ---
LIVE_SWEEPS = deque(maxlen=LIVE_SWEEPS_MAXLEN)
ZMQ_STATUS = "WAITING..."
MARKET_LEVELS_FILE = "market_levels.json"
MARKET_STRUCTURE = {"spy_price": 0.0, "spx_price": 0.0, "current_basis": 0.0}

# --- SENTIMENT TRACKING ---
SENTIMENT_SCORES = {"SPY": 0, "SPX": 0}
SEEN_TRADES_SENT = set()
LAST_RESET_DATE = None
SENTIMENT_STATE_FILE = "sweeps_v1_sentiment.json"

def load_sentiment_state():
    global SENTIMENT_SCORES, SEEN_TRADES_SENT, LAST_RESET_DATE
    if os.path.exists(SENTIMENT_STATE_FILE):
        try:
            with open(SENTIMENT_STATE_FILE, 'r') as f:
                data = json.load(f)
            
            saved_date = data.get('date')
            today = get_today_str()
            
            if saved_date == today:
                SENTIMENT_SCORES = data.get('scores', {"SPY": 0, "SPX": 0})
                SEEN_TRADES_SENT = set(data.get('seen', []))
                LAST_RESET_DATE = today
                print(f"[SENTIMENT] Loaded V1 State: {SENTIMENT_SCORES}")
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
            "date": get_today_str(),
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
    today = get_today_str()
    if LAST_RESET_DATE != today:
        SEEN_TRADES_SENT.clear()
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
    except Exception as e:
        print(f"State Dump Error: {e}")
        try: os.remove(temp_file)
        except: pass

# --- HELPERS ---
def get_ny_time(): return datetime.datetime.now(ET)
def get_active_trading_date():
    d = get_ny_time().date()
    while d.weekday() >= 5: d -= datetime.timedelta(days=1)
    return d

def get_today_str(): return get_active_trading_date().strftime("%Y-%m-%d")

def is_from_today(ts):
    if not ts: return False
    try: 
        if isinstance(ts, (int, float)):
            trade_date = datetime.datetime.fromtimestamp(ts, tz=UTC).astimezone(ET).date()
        elif isinstance(ts, str):
            trade_date = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET).date()
        else: return False
        return trade_date == get_active_trading_date()
    except: return False

def safe_float(v):
    try: return float(v) if v is not None else 0.0
    except: return 0.0

def safe_int(v):
    try: return int(float(v)) if v is not None else 0 
    except: return 0

def fmt_notional(value, show_plus=False):
    if value is None: return "N/A"
    try: v = abs(float(value))
    except: return "N/A"
    s = f"${v/1e9:.2f}B" if v>=1e9 else (f"${v/1e6:.1f}M" if v>=1e6 else (f"${v/1e3:.1f}K" if v>=1e3 else f"${v:.0f}"))
    if value < 0: s = "-" + s
    elif value > 0 and show_plus: s = "+" + s
    elif value == 0: return "$0"
    return s

def parse_option_chain(chain_symbol: str):
    if not chain_symbol: return None, None, None
    try:
        match = re.search(r'(\d{6})([CP])([\d\.]+)$', chain_symbol)
        if match:
            date_str, type_char, strike_str = match.groups()
            expiry = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
            otype = "CALL" if type_char == 'C' else "PUT"
            if len(strike_str) == 8 and "." not in strike_str: strike = float(strike_str) / 1000
            else: strike = float(strike_str)
            return expiry, otype, strike
        return None, None, None
    except: return None, None, None

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

def score_sweep(s_data: dict, market: dict, sentiment: str) -> tuple[int, list]:
    score = 0; notes = []
    try:
        prem = s_data['total_premium']
        dte = s_data['parsed_dte']
        strike = s_data['parsed_strike']
        otype = s_data['parsed_type']
        
        # FIX: Look-ahead bias. Use trade's underlying price if available.
        ref_price = s_data.get('underlying_price') or market.get("spy_price", 0)
        
        vol = s_data['total_size']
        oi = s_data['open_interest']
        
        if oi > 0:
            voi = vol / oi
            if voi > 2.0: score += 2; notes.append(f"FRESH({voi:.1f}x)")
            elif voi > 1.2: score += 1
            
            # Opening/Closing Logic
            if vol > oi: 
                score += 2; notes.append("OPENING") # High Signal
            elif vol < oi:
                notes.append("AMBIGUOUS") # Dim in UI

        if dte >= 30: score += 2; notes.append("SWING")
        elif dte == 0: score += 1; notes.append("0DTE") 
        
        if dte <= 1 and prem < 100_000: score -= 1 

        if s_data['ticker'] in ["SPX", "SPXW"]:
            if prem >= 1_000_000: score += 3; notes.append("SIZE: >$1M")
            elif prem >= 500_000: score += 1; notes.append("SIZE: >$500k")
        else:
            if prem >= 500_000: score += 3; notes.append("SIZE: >$500k")
            elif prem >= 150_000: score += 1; notes.append("SIZE: >$150k")

        # OTM Check using ref_price
        if ref_price > 0:
            is_otm = (otype == 'CALL' and strike > ref_price) or (otype == 'PUT' and strike < ref_price)
            if is_otm: score += 1; notes.append("OTM")
        
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
            # Shorten the note: Z(16.3s|u=50k|s=1k)
            notes.append(f"Z-PREM({z_prem:.1f}σ|μ={fmt_notional(m)}|σ={fmt_notional(s)})")
        
    except Exception as e: notes.append(f"Err: {str(e)[:10]}")
    return score, notes

class NexusSweeps(App):
    CSS = """
    Screen { layout: vertical; }
    HeaderBox { dock: top; height: 4; background: $surface-darken-1; border-bottom: solid $primary; layout: horizontal; align-vertical: middle; padding-left: 1; }
    #header_lbl { width: 1fr; content-align: center middle; height: 100%; }
    #btn_snapshot { margin-right: 1; }
    Footer { dock: bottom; height: 1; }
    #log-container { dock: bottom; height: 8; border-top: solid $secondary-darken-2; }
    Log { height: 100%; width: 100%; background: $surface; color: $text; overflow-y: scroll; }
    
    /* NEW LAYOUT */
    #main-view { height: 1fr; width: 100%; layout: horizontal; }
    #spy-container { width: 50%; height: 100%; border-right: solid $secondary; }
    #spx-container { width: 50%; height: 100%; }
    
    .half-height { height: 50%; width: 100%; border-bottom: solid $secondary-darken-2; }
    .section-header { height: 1; width: 100%; background: $primary-darken-2; color: white; text-align: center; text-style: bold; }
    
    SweepTable { height: 1fr; width: 100%; }
    """
    zmq_ctx = zmq.asyncio.Context(); select_sock = None
    last_snapshot_hour = -1 
    
    # Rolling Stats for Stationarity (Time-Based, 30 Days)
    stats_premium = RollingStats(window_days=30)
    stats_vol = RollingStats(window_days=30) 

    class HeaderBox(Container):
        def compose(self) -> ComposeResult:
            yield Static(id="header_lbl"); yield Button("SNAPSHOT", id="btn_snapshot", variant="warning")
        def on_mount(self): self.set_interval(POLL_FAST_TICK_SECONDS, self.update_header)
        def update_header(self):
            now = get_ny_time(); c = lambda v: "green" if v>=0 else "red"
            stats = {k: {"bull":0,"bear":0} for k in ["SPY","SPX","D0","D1","TOTAL"]}
            
            # For State Dumping
            bull_list = []
            bear_list = []
            total_prem_dump = 0.0

            for s in list(LIVE_SWEEPS):
                if not is_from_today(s.get('executed_at')): continue
                p = s.get('total_premium',0); sent = s.get('sentiment_str','MID'); otype=s.get('parsed_type','N/A'); dte=s.get('parsed_dte',-1)
                
                total_prem_dump += p

                # Aggressor Weighting
                aggressor_tag, weight = calculate_aggressor_score(s)
                weighted_prem = p * weight
                
                bkt = "bull" if (sent=="BUY" and otype=="CALL") or (sent=="SELL" and otype=="PUT") else "bear"
                
                if bkt == "bull": bull_list.append(s)
                else: bear_list.append(s)

                k = "SPX" if "SPX" in s.get('ticker','') else "SPY"
                stats[k][bkt]+=weighted_prem; stats['TOTAL'][bkt]+=weighted_prem
                if dte<=SHORT_DTE_CUTOFF: stats['D0'][bkt]+=weighted_prem
                else: stats['D1'][bkt]+=weighted_prem

            spy_n = stats['SPY']['bull'] - stats['SPY']['bear']
            spx_n = stats['SPX']['bull'] - stats['SPX']['bear']
            d0_n = stats['D0']['bull'] - stats['D0']['bear']
            d1_n = stats['D1']['bull'] - stats['D1']['bear']
            tot_n = stats['TOTAL']['bull'] - stats['TOTAL']['bear']
            
            status_style = "green" if ZMQ_STATUS == "CONNECTED" else "red"
            c_spy = "green" if SENTIMENT_SCORES["SPY"] >= 0 else "red"
            c_spx = "green" if SENTIMENT_SCORES["SPX"] >= 0 else "red"
            
            l1 = f" [bold]Nexus Tape (0-3 DTE)[/] | {now.strftime('%H:%M:%S ET')} | [{c_spy}]SPY:{SENTIMENT_SCORES['SPY']}[/] [{c_spx}]SPX:{SENTIMENT_SCORES['SPX']}[/] | ZMQ: [{status_style}]{ZMQ_STATUS}[/]"
            l2 = (f" SPY Net: [{c(spy_n)}]{fmt_notional(spy_n,True)}[/] | SPX Net: [{c(spx_n)}]{fmt_notional(spx_n,True)}[/]  [dim]||[/]  "
                  f"0-3D: [{c(d0_n)}]{fmt_notional(d0_n,True)}[/] | 3+D: [{c(d1_n)}]{fmt_notional(d1_n,True)}[/]  [dim]||[/]  "
                  f"TOT: [{c(tot_n)}]{fmt_notional(tot_n,True)}[/]")
            self.query_one("#header_lbl", Static).update(Text.from_markup(f"{l1}\n{l2}"))

            # --- ANTIGRAVITY STATE DUMP ---
            current_state = {
                "total_premium": total_prem_dump,
                "bullish_flow_list": bull_list,
                "bearish_flow_list": bear_list,
                "sentiment_scores": SENTIMENT_SCORES,
                "timestamp": now.isoformat()
            }
            antigravity_dump("nexus_sweeps_v1.json", current_state)

    class SweepTable(DataTable):
        sweeps_on_display = []

        def __init__(self, tickers=None, dte_mode="ALL", **kwargs): 
            super().__init__(**kwargs)
            self.tickers = tickers or []
            self.dte_mode = dte_mode

        def on_mount(self):
            # Removed "Exp" and "Details" columns
            self.add_columns("Prio", "Age", "Time", "Tkr", "DTE", "Strike", "Type", "Side", "Premium", "V/OI", "Notes")
            self.cursor_type = "row"; self.set_interval(1.0, self.update_table)
            self.last_displayed_ids = [] # [FIX] State for equality check

        def update_table(self):
            # REMOVED: if self.scroll_y > 0: return (Causing empty tables?)
            if not LIVE_SWEEPS: return
            
            # 1. Filter
            to_show = [s for s in list(LIVE_SWEEPS) if is_from_today(s.get('executed_at'))]
            
            # Filter by Ticker
            if self.tickers:
                to_show = [s for s in to_show if s.get('ticker') in self.tickers]
            
            # Filter by DTE
            if self.dte_mode == "SHORT": to_show = [s for s in to_show if s.get('parsed_dte', -1) <= SHORT_DTE_CUTOFF]
            elif self.dte_mode == "LONG": to_show = [s for s in to_show if s.get('parsed_dte', -1) > SHORT_DTE_CUTOFF]
            
            # [NEW] Filter by Vol/OI > 1 (High Conviction / Opening)
            # Include if OI is 0 (New Position)
            to_show = [s for s in to_show if s.get('open_interest', 0) == 0 or s.get('total_size', 0) > s.get('open_interest', 0)]
            
            to_show.sort(key=lambda s: s.get('priority_score', 0), reverse=True)
            
            # OPTIMIZATION: Limit to Top 50 rows to prevent UI lag
            to_show = to_show[:50]
            
            # [FIX] SNAPBACK PREVENTION: Only update if data changed
            current_ids = [f"{s.get('option_chain')}_{s.get('executed_at')}_{s.get('total_size')}" for s in to_show]
            if current_ids == self.last_displayed_ids:
                return
            self.last_displayed_ids = current_ids
            
            save_cursor_row = self.cursor_coordinate.row
            save_scroll_y = self.scroll_y

            self.sweeps_on_display = to_show; self.clear()
            for i, s in enumerate(to_show):
                try:
                    ts = float(s.get('executed_at', 0))
                    tm_str = datetime.datetime.fromtimestamp(ts, tz=ET).strftime("%H:%M:%S")
                except: tm_str = "--:--:--"
                otype = s.get('parsed_type', 'N/A'); ost = "green" if otype=='CALL' else "red"
                sent = s.get('sentiment_str', 'MID'); sst = "green" if sent=='BUY' else ("red" if sent=='SELL' else "white")
                
                now_ts = datetime.datetime.now(ET).timestamp()
                age_sec = max(0, int(now_ts - ts))
                if age_sec < 60: age_str = f"{age_sec}s"
                elif age_sec < 3600: age_str = f"{age_sec//60}m {age_sec%60}s"
                else: age_str = f"{age_sec//3600}h {(age_sec%3600)//60}m"
                
                sc = s.get('priority_score', 0)
                oi = s.get('open_interest', 0); size = s.get('total_size', 0)
                voi_str = f"{size/oi:.1f}x" if oi > 0 else "NEW"
                stk = s.get('parsed_strike', 0)
                basis = MARKET_STRUCTURE.get('current_basis', 0.0)
                if "SPX" in s.get('ticker', ''):
                    if abs(basis) > 0.1: spy_equiv = (stk - basis) / 10
                    else: spy_equiv = stk / 10
                    stk_s = f"${stk:,.0f} (SPY {spy_equiv:.1f})"
                else:
                    stk_s = f"${stk:,.2f}".replace(".00", "")

                if sc >= 5: sc_render = Text(f"{sc}", style="bold red")
                elif sc >= 3: sc_render = Text(f"{sc}", style="bold yellow")
                elif sc >= 1: sc_render = Text(f"{sc}", style="bold blue")
                else: sc_render = Text(f"{sc}", style="dim")

                note_badges = []
                raw_notes = s.get('priority_notes', '').split(', ')
                for n in raw_notes:
                    if not n: continue
                    if "OTM" in n: note_badges.append(f"[bold green]{n}[/]")
                    elif "SWING" in n: note_badges.append(f"[bold blue]{n}[/]")
                    elif "SIZE" in n: note_badges.append(f"[bold yellow]{n}[/]")
                    elif "FRESH" in n: note_badges.append(f"[bold cyan]{n}[/]")
                    elif "Z-PREM" in n: note_badges.append(f"[bold magenta]{n}[/]")
                    elif "0DTE" in n: note_badges.append(f"[bold red]{n}[/]")
                    elif "OPENING" in n: note_badges.append(f"[bold gold1]{n}[/]")
                    elif "INSTITUTIONAL URGENCY" in n: note_badges.append(f"[bold red blink]{n}[/]")
                    elif "BURST" in n: note_badges.append(f"[bold orange1]{n}[/]")
                    else: note_badges.append(f"[dim]{n}[/]")
                notes_render = Text.from_markup(" ".join(note_badges))
                
                row_style = "dim" if "AMBIGUOUS" in raw_notes else ""

                # Removed Exp and Details from add_row
                self.add_row(sc_render, Text(age_str, style="dim"), tm_str, s.get('ticker','?'), str(s.get('parsed_dte','-')),
                             stk_s, Text(otype, style=ost), Text(sent, style=sst),
                             Text(fmt_notional(s.get('total_premium',0)), style="bold "+sst), Text(voi_str),
                             notes_render, key=str(i))
                
                if row_style == "dim": pass 
            
            if save_cursor_row > 0 and save_cursor_row < self.row_count:
                self.move_cursor(row=save_cursor_row, animate=False)
            self.call_after_refresh(self.scroll_to, y=save_scroll_y, animate=False)

    def compose(self) -> ComposeResult:
        yield self.HeaderBox()
        with Container(id="main-view"):
            # SPY CONTAINER (Left)
            with Container(id="spy-container"):
                # Top: Short DTE (Full Height now)
                with Vertical():
                    yield Static("SPY 0-3 DTE (The Tape)", classes="section-header")
                    yield self.SweepTable(id="tbl_spy_short", tickers=["SPY"], dte_mode="SHORT")
            
            # SPX CONTAINER (Right)
            with Container(id="spx-container"):
                # Top: Short DTE (Full Height now)
                with Vertical():
                    yield Static("SPX 0-3 DTE (The Tape)", classes="section-header")
                    yield self.SweepTable(id="tbl_spx_short", tickers=["SPX", "SPXW"], dte_mode="SHORT")

        with Container(id="log-container"): yield Log(id="app-log")
        yield Footer()

    async def on_mount(self):
        self.log_msg("Init V1 Classic (Snapback Fixed)..."); self.update_market_structure()
        
        load_sentiment_state()
        
        # HEADLESS MODE: Fetch, Dump, Loop
        if getattr(self, "HEADLESS", False):
            self.log_msg("HEADLESS MODE: Starting Loop...")
            while True:
                self.log_msg("HEADLESS: Fetching Backfill...")
                await self.fetch_backfill_logic()
                self.log_msg("HEADLESS: Dumping State...")
                # self.dump_state_to_json() # V1 dumps inside update_header, but we need to trigger it manually or rely on update_header loop?
                # V1 update_header runs on interval. In headless, we don't have a UI loop ticking?
                # Textual apps DO run the message loop even in headless.
                # But let's be explicit like V2.
                # Actually, V1's fetch_backfill calls filter_and_process which appends to LIVE_SWEEPS.
                # We need to dump that.
                self.manual_dump()
                self.log_msg("HEADLESS: Sleeping 5m...")
                await asyncio.sleep(300)
            return

        self.fetch_backfill()
        try: self.select_sock = self.zmq_ctx.socket(zmq.PUB); self.select_sock.bind(f"tcp://127.0.0.1:{ZMQ_SELECT_PORT}")
        except: pass
        self.set_interval(60.0, self.check_auto_snapshot)
        self.stream_zmq_data()

    def manual_dump(self):
        # Logic extracted from update_header for headless dumping
        now = get_ny_time()
        bull_list = []; bear_list = []; total_prem_dump = 0.0
        for s in list(LIVE_SWEEPS):
            if not is_from_today(s.get('executed_at')): continue
            p = s.get('total_premium',0); sent = s.get('sentiment_str','MID'); otype=s.get('parsed_type','N/A')
            total_prem_dump += p
            bkt = "bull" if (sent=="BUY" and otype=="CALL") or (sent=="SELL" and otype=="PUT") else "bear"
            if bkt == "bull": bull_list.append(s)
            else: bear_list.append(s)
        
        current_state = {
            "total_premium": total_prem_dump,
            "bullish_flow_list": bull_list,
            "bearish_flow_list": bear_list,
            "sentiment_scores": SENTIMENT_SCORES,
            "timestamp": now.isoformat()
        }
        antigravity_dump("nexus_sweeps_v1.json", current_state)

    @work()
    async def fetch_backfill(self):
        await self.fetch_backfill_logic()

    async def fetch_backfill_logic(self):
        url = "https://api.unusualwhales.com/api/screener/option-contracts"
        headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        today_str = get_today_str()
        loop = asyncio.get_event_loop()
        for t in TICKERS_TO_SHOW:
            try:
                th = PREMIUM_THRESHOLDS.get(t, 50000)
                p = {'ticker_symbol':t, 'order':'premium', 'order_direction':'desc', 'limit':100, 'min_dte':MIN_DTE, 'max_dte':MAX_DTE, 'min_premium':th, 'date': today_str}
                r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, params=p, timeout=5))
                if r.status_code == 200:
                    cnt = 0
                    for i in reversed(r.json().get('data', [])):
                        raw_ts = i.get('last_fill') or i.get('last_trade_time') or i.get('timestamp') or i.get('date') or 0
                        if isinstance(raw_ts, str): ts_val = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp()
                        else: ts_val = raw_ts
                        if True: # [DEBUG] Bypassing date check to force data load
                            # [PATCHED] Added 'delta' and 'gamma' capture
                            delta = safe_float(i.get('greeks', {}).get('delta') or i.get('delta'))
                            gamma = safe_float(i.get('greeks', {}).get('gamma') or i.get('gamma'))
                            m = {'ticker': t, 'total_premium': safe_float(i.get('premium') or i.get('total_premium')), 'option_chain': i.get('symbol') or i.get('option_symbol'), 'executed_at': ts_val, 'total_size': safe_int(i.get('size') or i.get('volume')), 'open_interest': safe_int(i.get('open_interest')), 'price': safe_float(i.get('price') or i.get('close')), 'underlying_price': safe_float(i.get('underlying_price') or i.get('stock_price')), 'total_ask_side_prem': safe_float(i.get('ask_side_volume')) * safe_float(i.get('avg_price')) * 100, 'total_bid_side_prem': safe_float(i.get('bid_side_volume')) * safe_float(i.get('avg_price')) * 100, 'delta': delta, 'gamma': gamma}
                            self.filter_and_process(m, is_history=True); cnt += 1
                    self.log_msg(f"BACKFILL: {t} -> {cnt} rows")
            except Exception as e: self.log_msg(f"BF Err {t}: {e}")

    def check_auto_snapshot(self):
        now = get_ny_time()
        target_hours = [10, 14, 18]
        if now.hour in target_hours and now.minute < 5:
            if self.last_snapshot_hour != now.hour:
                self.save_snapshot()
                self.last_snapshot_hour = now.hour
                self.log_msg(f"Auto-Snapshot Triggered ({now.strftime('%H:%M')})")
        elif now.hour not in target_hours:
            self.last_snapshot_hour = -1

    def save_snapshot(self):
        if not LIVE_SWEEPS: return
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_dir = Path("snapshots_sweeps"); save_dir.mkdir(exist_ok=True)
        csv_filename = save_dir / f"{timestamp}_sweeps_screener_v1.csv"
        try:
            today_sweeps = [s for s in list(LIVE_SWEEPS) if is_from_today(s.get('executed_at'))]
            if not today_sweeps: return
            df = pd.DataFrame(today_sweeps)
            cols = ['ticker', 'parsed_expiry', 'parsed_dte', 'parsed_strike', 'parsed_type', 'sentiment_str', 'total_premium', 'priority_score', 'priority_notes', 'price', 'total_size', 'open_interest', 'delta', 'gamma']
            existing_cols = [c for c in cols if c in df.columns]
            if existing_cols: df = df[existing_cols]
            df.to_csv(csv_filename, index=False)
            print(f"[PATCHED] Added 'delta' column to {csv_filename} output.")
            self.notify(f"Snapshot Saved: {timestamp}")
        except Exception as e: self.log_msg(f"Snapshot Fail: {e}")

    @on(Button.Pressed, "#btn_snapshot")
    def on_manual_snapshot(self): self.save_snapshot()

    @work()
    async def fetch_backfill(self):
        url = "https://api.unusualwhales.com/api/screener/option-contracts"
        headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        today_str = get_today_str()
        loop = asyncio.get_event_loop()
        for t in TICKERS_TO_SHOW:
            try:
                th = PREMIUM_THRESHOLDS.get(t, 50000)
                p = {'ticker_symbol':t, 'order':'premium', 'order_direction':'desc', 'limit':100, 'min_dte':MIN_DTE, 'max_dte':MAX_DTE, 'min_premium':th, 'date': today_str}
                r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, params=p, timeout=5))
                if r.status_code == 200:
                    cnt = 0
                    for i in reversed(r.json().get('data', [])):
                        raw_ts = i.get('last_fill') or i.get('last_trade_time') or i.get('timestamp') or i.get('date') or 0
                        if isinstance(raw_ts, str): ts_val = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp()
                        else: ts_val = raw_ts
                        if is_from_today(ts_val):
                            # [PATCHED] Added 'delta' and 'gamma' capture
                            delta = safe_float(i.get('greeks', {}).get('delta') or i.get('delta'))
                            gamma = safe_float(i.get('greeks', {}).get('gamma') or i.get('gamma'))
                            m = {'ticker': t, 'total_premium': safe_float(i.get('premium') or i.get('total_premium')), 'option_chain': i.get('symbol') or i.get('option_symbol'), 'executed_at': ts_val, 'total_size': safe_int(i.get('size') or i.get('volume')), 'open_interest': safe_int(i.get('open_interest')), 'price': safe_float(i.get('price') or i.get('close')), 'underlying_price': safe_float(i.get('underlying_price') or i.get('stock_price')), 'total_ask_side_prem': safe_float(i.get('ask_side_volume')) * safe_float(i.get('avg_price')) * 100, 'total_bid_side_prem': safe_float(i.get('bid_side_volume')) * safe_float(i.get('avg_price')) * 100, 'delta': delta, 'gamma': gamma}
                            self.filter_and_process(m, is_history=True); cnt += 1
                    self.log_msg(f"BACKFILL: {t} -> {cnt} rows")
            except Exception as e: self.log_msg(f"BF Err {t}: {e}")

    @work()
    async def stream_zmq_data(self):
        global ZMQ_STATUS
        while True:
            s = None
            try:
                s = self.zmq_ctx.socket(zmq.SUB)
                s.connect(f"tcp://127.0.0.1:{ZMQ_PORT}")
                s.setsockopt_string(zmq.SUBSCRIBE, ZMQ_TOPIC)
                ZMQ_STATUS = "CONNECTED"
                self.log_msg("ZMQ: Connected to Flow Stream.")
                
                while True:
                    try:
                        msg = await s.recv_multipart()
                        if len(msg) < 2 or not msg[1]: continue
                        
                        try:
                            d = json.loads(msg[1].decode('utf-8'))
                            ts = d.get('executed_at') or d.get('timestamp') or datetime.datetime.now(ET).timestamp()
                            if is_from_today(ts): self.filter_and_process(d, is_history=False)
                        except json.JSONDecodeError as e:
                            if DEBUG_MODE: self.log_msg(f"JSON Err: {e}")
                        except Exception as e:
                            if DEBUG_MODE: self.log_msg(f"Process Err: {e}")
                            
                    except Exception as e:
                        self.log_msg(f"Stream Loop Err: {e}")
                        break # Break inner loop to trigger reconnect
                        
            except Exception as e: 
                ZMQ_STATUS = "ERROR"
                self.log_msg(f"ZMQ Connection Lost: {e}. Retrying in 5s...")
                
            finally:
                if s: 
                    try: s.close()
                    except: pass
            
            await asyncio.sleep(5) # Backoff before reconnect

    @work(thread=True)
    def update_market_structure(self):
        global MARKET_STRUCTURE
        while True:
            try:
                if os.path.exists(MARKET_LEVELS_FILE):
                    with open(MARKET_LEVELS_FILE,'r') as f: MARKET_STRUCTURE.update(json.load(f))
                spy = MARKET_STRUCTURE.get('spy_price', 0); spx = MARKET_STRUCTURE.get('spx_price', 0)
                if spy > 0 and spx > 0: MARKET_STRUCTURE['current_basis'] = spx - (spy * 10)
            except: pass
            time.sleep(1)

    def filter_and_process(self, d: dict, is_history=False):
        try:
            # [HARDENING] Normalize Keys (Premium)
            d['total_premium'] = safe_float(d.get('total_premium') or d.get('premium'))
            d['total_size'] = safe_int(d.get('total_size') or d.get('volume') or d.get('size'))
            d['open_interest'] = safe_int(d.get('open_interest'))
            d['price'] = safe_float(d.get('price'))
            d['total_ask_side_prem'] = safe_float(d.get('total_ask_side_prem'))
            d['total_bid_side_prem'] = safe_float(d.get('total_bid_side_prem'))
            
            # [HARDENING] Normalize Timestamp (executed_at)
            raw_ts = d.get('executed_at') or d.get('timestamp') or 0
            if isinstance(raw_ts, str):
                 try: d['executed_at'] = datetime.datetime.fromisoformat(raw_ts.replace("Z", "+00:00")).timestamp()
                 except: d['executed_at'] = datetime.datetime.now(ET).timestamp()
            elif isinstance(raw_ts, (int, float)):
                 d['executed_at'] = float(raw_ts)
            else:
                 d['executed_at'] = datetime.datetime.now(ET).timestamp()
            
            # [PATCHED] Added 'delta' capture
            if 'delta' not in d:
                d['delta'] = safe_float(d.get('greeks', {}).get('delta') or d.get('delta'))
            
            # Extract Bid/Ask for Aggressor Score
            d['bid'] = safe_float(d.get('bid') or d.get('bid_price'))
            d['ask'] = safe_float(d.get('ask') or d.get('ask_price'))
            
            if not is_from_today(d.get('executed_at')): return
            tkr = d.get('ticker')
            if tkr not in TICKERS_TO_SHOW or d['total_premium'] < PREMIUM_THRESHOLDS.get(tkr, 50000): return
            chain = d.get('option_chain'); exp, otype, stk = parse_option_chain(chain)
            if not all([exp, otype, stk]): return
            try: dte = (datetime.date.fromisoformat(exp) - datetime.datetime.now(ET).date()).days
            except: dte = -1
            d.update({'parsed_expiry':exp, 'parsed_type':otype, 'parsed_strike':stk, 'parsed_dte':dte})
            
            # --- BURST DETECTION (Mega-Sweep) ---
            if LIVE_SWEEPS:
                last_trade = LIVE_SWEEPS[0]
                if (last_trade['option_chain'] == d['option_chain'] and 
                    abs(d['executed_at'] - last_trade['executed_at']) < 0.5):
                    
                    # MERGE into last trade
                    last_trade['total_size'] += d['total_size']
                    last_trade['total_premium'] += d['total_premium']
                    last_trade['is_burst'] = True
                    
                    # Re-score
                    sc, n = score_sweep(last_trade, MARKET_STRUCTURE, last_trade['sentiment_str'])
                    last_trade['priority_score'] = sc
                    last_trade['priority_notes'] = ", ".join(n)
                    return # Skip adding 'd'

            # Update Rolling Stats & Calculate Z-Score (Leakage Fixed inside process method)
            # We pass the timestamp of the trade, not current time
            ts_dt = datetime.datetime.fromtimestamp(d['executed_at'], tz=ET)
            d['z_premium'], d['mean_premium'], d['std_premium'] = self.stats_premium.process(ts_dt, d['total_premium'])
            d['z_vol'], d['mean_vol'], d['std_vol'] = self.stats_vol.process(ts_dt, d['total_size'])

            sent = "BUY" if d['total_ask_side_prem'] > d['total_bid_side_prem'] else ("SELL" if d['total_bid_side_prem'] > d['total_ask_side_prem'] else "MID")
            d['sentiment_str'] = sent
            sc, n = score_sweep(d, MARKET_STRUCTURE, sent); d['priority_score'] = sc; d['priority_notes'] = ", ".join(n)
            
            # Update Global Sentiment
            update_cumulative_sentiment(d)
            
            LIVE_SWEEPS.appendleft(d)
            
            # OUTPUT FOR SHADOW BOT (Log File)
            # print(json.dumps(d, default=str), flush=True)
            try:
                log_dir = Path("logs"); log_dir.mkdir(exist_ok=True)
                with open(log_dir / "sweeps_v1.log", "a") as f:
                    f.write(json.dumps(d, default=str) + "\n")
            except: pass
            
        except: pass

    def log_msg(self, m): self.query_one(Log).write(f"[{datetime.datetime.now(ET).strftime('%H:%M:%S')}] {m}")
    
    @on(DataTable.RowSelected)
    def on_sel(self, e: DataTable.RowSelected):
        if not self.select_sock: return
        try:
            t_id = e.data_table.id; tbl = self.query_one(f"#{t_id}", self.SweepTable)
            s = tbl.sweeps_on_display[int(e.row_key.value)]
            conf = "🟢 BULL" if s['sentiment_str']=="BUY" else ("🔴 BEAR" if s['sentiment_str']=="SELL" else "⚪ MID")
            be = s['parsed_strike'] + s['price'] if s['parsed_type']=='CALL' else s['parsed_strike'] - s['price']
            m = {'symbol': s['option_chain'], 'exp': s['parsed_expiry'], 'dte': s['parsed_dte'], 'stk': s['parsed_strike'], 'type': s['parsed_type'], 'prem': s['total_premium'], 'mkt': s['price'], 'vol': s['total_size'], 'conf': conf, 'is_ml': False, 'oi': s['open_interest'], 'voi_ratio': s['total_size'] / s['open_interest'] if s['open_interest'] > 0 else 0, 'pc_ratio_vol': 0, 'pc_ratio_oi': 0, 'theo': s['price'], 'edge': 0, 'win': -1, 'be': be}
            self.select_sock.send_multipart([ZMQ_SELECT_TOPIC, json.dumps(m).encode('utf-8')])
            self.notify(f"Sent {m['symbol']}")
        except: pass

if __name__ == "__main__": 
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")
    args = parser.parse_args()
    DEBUG_MODE = args.debug
    
    app = NexusSweeps()
    app.HEADLESS = args.headless
    app.run()