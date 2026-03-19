"""
import nexus_lock
nexus_lock.enforce_singleton()
Simple Stable Macro Dashboard (Nexus Integrated) - REVISED
Includes:
- Optimized ORATS History (Date Range)
- ZMQ Auto-Reconnection
- Spot Gamma Calculation (FIXED)
- IV Rank & Skew Logic
- LOGIC FIX: Net Premium Fail-over (Bull-Bear -> Call-Put) to prevent $0 readings.
- FILE LOGGING ENABLED (viewer_debug.log)
"""

# --- Core Python / TUI ---
import asyncio
import datetime
import os
import json
import ssl
import math
import sys
import traceback
import time
from datetime import timedelta, time as dt_time
from collections import deque

# --- Third-Party ---
import requests 
import aiohttp 
import pandas as pd
import numpy as np
import zmq
import zmq.asyncio

from supabase_bridge import get_supabase_client

try:
    import pytz
    ET = pytz.timezone('US/Eastern')
except ImportError:
    print("Error: 'pytz' not found. Please run 'pip install pytz'")
    sys.exit(1)

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Log
from textual.containers import Horizontal, Vertical, Container, Grid
from rich.text import Text
from rich.panel import Panel
from rich.table import Table 
from rich.console import Group
from rich import box
from textual import work
from textual.reactive import reactive

# --- ============================== ---
# --- 1. UNIFIED CONFIGURATION ---
# --- ============================== ---

# --- API Keys ---
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

# --- Tickers ---
TICKER_EQUITY = "SPY"
TICKERS_FUTURES = ["@ES", "@NQ", "MESM26"]
TICKERS_SECTORS = ['XLK', 'XLF', 'XLV', 'XLY', 'XLP', 'XLE', 'XLC', 'XLI', 'XLB', 'XLRE', 'XLU']
ALL_TICKERS_SUB = [TICKER_EQUITY, "$SPX.X", "$VIX.X"] + TICKERS_FUTURES + TICKERS_SECTORS

# --- Behavior ---
# --- Behavior ---
POLL_FAST_TICK_SECONDS = 1.0
POLL_MACRO_SECONDS = 300  # 5 minutes

# --- Global State ---
PRICE_DATA = {t: {'curr': None, 'chg_pct': 0.0, 'net_chg': 0.0} for t in ALL_TICKERS_SUB}
LAST_MACRO_DATA = {
    'iv': 0, 
    'iv_rank': 0,   
    'skew': 0,      
    't_dates': [], 'orats_price': 0.0,
    'gex_summaries': [],
    'uw_flow': {},
    'atr': 0.0,
    'rsi': 0.0,
    'flow_z_score': 0.0,
    'divergence': None
}
NEXUS_STATUS = "WAITING..."

# --- ============================== ---
# --- 2. HELPER FUNCTIONS ---
# --- ============================== ---

def get_ny_time(): 
    return datetime.datetime.now(ET)

import uuid

def antigravity_dump(filename, data_dictionary):
    """
    Atomically dumps data and prints a heartbeat log.
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

def is_analysis_time(): 
    now = get_ny_time()
    if now.weekday() >= 5: return "SLEEP"
    
    t = now.time()
    # Market Hours: 9:30 - 16:00
    if datetime.time(9, 30) <= t <= datetime.time(16, 0):
        return "ACTIVE"
    # Extended Hours: 8:00 - 9:30 OR 16:00 - 16:15
    if (datetime.time(8, 0) <= t < datetime.time(9, 30)) or \
       (datetime.time(16, 0) < t <= datetime.time(16, 15)):
        return "SLOW"
        
    return "SLEEP"

def api_retry(func):
    """Decorator for Exponential Backoff."""
    def wrapper(*args, **kwargs):
        wait_times = [5, 10, 20, 40, 60]
        for i, wait in enumerate(wait_times + [60]):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if i == len(wait_times): raise e # Give up
                
                # Log if possible
                if len(args) > 0 and hasattr(args[0], 'log_msg'):
                    args[0].log_msg(f"[WARN] API Error: {e}. Cooling down for {wait}s...")
                else:
                    print(f"[WARN] API Error: {e}. Cooling down for {wait}s...")
                
                time.sleep(wait)
    return wrapper

def get_trading_date(ref_date=None):
    if ref_date is None: ref_date = get_ny_time().date()
    while ref_date.weekday() >= 5: 
        ref_date -= timedelta(days=1)
    return ref_date

def get_next_n_trading_dates(start_date, n):
    dates = []
    current_date = start_date
    
    # Hardcoded Market Holidays for 2025/2026
    holidays = [
        datetime.date(2025, 1, 1), datetime.date(2025, 1, 20), datetime.date(2025, 2, 17),
        datetime.date(2025, 4, 18), datetime.date(2025, 5, 26), datetime.date(2025, 6, 19),
        datetime.date(2025, 7, 4), datetime.date(2025, 9, 1), datetime.date(2025, 11, 27),
        datetime.date(2025, 12, 25), datetime.date(2026, 1, 1), datetime.date(2026, 1, 19), 
        datetime.date(2026, 2, 16), datetime.date(2026, 4, 3), datetime.date(2026, 5, 25)
    ]
    
    while len(dates) < n:
        if current_date.weekday() < 5 and current_date not in holidays:
            dates.append(current_date)
        current_date += timedelta(days=1)
    return dates

# --- ACCUMULATED PREMIUM TRACKER ---
def track_accumulated_premium(orats_chain, spot_price, state_file="viewer_premium_state.json"):
    """Tracks incremental changes in Call/Put volume between scans."""
    today = get_trading_date().isoformat()
    state = {'date': today, 'cum_net_prem': 0.0, 'cum_net_delta': 0.0, 'volumes': {}}
    
    if os.path.exists(state_file):
        try:
            with open(state_file, 'r') as f:
                saved = json.load(f)
                if saved.get('date') == today:
                    state = saved
        except: pass
        
    prev_vols = state.get('volumes', {})
    new_vols = {}
    
    tick_net_prem = 0
    tick_net_delta = 0
    
    for item in orats_chain:
        try:
            stk = str(item.get('strike', 0)) + "_" + str(item.get('expirDate', ''))
            
            c_vol = float(item.get('callVolume', 0))
            p_vol = float(item.get('putVolume', 0))
            
            prev_c = float(prev_vols.get(stk, {}).get('c', 0))
            prev_p = float(prev_vols.get(stk, {}).get('p', 0))
            
            c_diff = max(0, c_vol - prev_c)
            p_diff = max(0, p_vol - prev_p)
            
            new_vols[stk] = {'c': c_vol, 'p': p_vol}
            
            if c_diff > 0 or p_diff > 0:
                c_mid = (float(item.get('callBidPrice', 0)) + float(item.get('callAskPrice', 0))) / 2
                if c_mid == 0: c_mid = (float(item.get('callBid', 0)) + float(item.get('callAsk', 0))) / 2
                
                p_mid = (float(item.get('putBidPrice', 0)) + float(item.get('putAskPrice', 0))) / 2
                if p_mid == 0: p_mid = (float(item.get('putBid', 0)) + float(item.get('putAsk', 0))) / 2
                
                c_del = float(item.get('callDelta', 0.5))
                if 'callDelta' not in item: c_del = float(item.get('delta', 0.5))
                p_del = float(item.get('putDelta', -0.5))
                
                spot_approx = float(item.get('stockPrice') or spot_price or 0)
                
                if c_diff > 0 and c_mid > 0:
                    tick_net_prem += (c_diff * c_mid * 100)
                    tick_net_delta += (c_diff * c_del * 100) # Raw Delta Shares
                if p_diff > 0 and p_mid > 0:
                    tick_net_prem -= (p_diff * p_mid * 100)
                    tick_net_delta += (p_diff * p_del * 100) # Raw Delta Shares
                    
        except: pass
        
    state['cum_net_prem'] += tick_net_prem
    state['cum_net_delta'] += tick_net_delta
    state['volumes'] = new_vols
    
    try:
        with open(state_file, 'w') as f: json.dump(state, f)
    except: pass
    
    return state['cum_net_prem'], state['cum_net_delta']

def fmt_notional(value, show_plus=False):
    if value is None or pd.isna(value) or not np.isfinite(value): return "N/A"
    val_abs = abs(value)
    if val_abs >= 1e9: s = f"${val_abs/1e9:.1f}B"
    elif val_abs >= 1e6: s = f"${val_abs/1e6:.1f}M"
    elif val_abs >= 1e3: s = f"${val_abs/1e3:.1f}K"
    else: s = f"${val_abs:.0f}"
    if value < 0: s = "-" + s
    elif value > 0 and show_plus: s = "+" + s
    elif value == 0: return "$0"
    return s

# --- NATIVE INDICATORS ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_atr(df, period=14):
    high = df['high']
    low = df['low']
    close = df['close']
    prev_close = close.shift()
    tr0 = abs(high - low)
    tr1 = abs(high - prev_close)
    tr2 = abs(low - prev_close)
    tr = pd.concat([tr0, tr1, tr2], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

# --- ============================== ---
# --- 3. LIVE DATA STREAMS (ZMQ) ---
# --- ============================== ---

async def stream_nexus_prices(app: App):
    """Listens to the TradeStation Nexus ZMQ stream with Auto-Reconnection."""
    global NEXUS_STATUS
    ctx = zmq.asyncio.Context()
    
    while True:
        sock = ctx.socket(zmq.SUB)
        try:
            sock.connect("tcp://localhost:5555")
            for t in ALL_TICKERS_SUB: 
                sock.setsockopt_string(zmq.SUBSCRIBE, t)
            
            NEXUS_STATUS = "CONNECTED"
            app.log_msg("Nexus ZMQ stream connected.")
            
            while True:
                msg = await sock.recv_multipart()
                sym = msg[0].decode()
                if sym in PRICE_DATA:
                    d = json.loads(msg[1])
                    if "Last" in d:
                        PRICE_DATA[sym]['curr'] = float(d['Last'])
                        PRICE_DATA[sym]['chg_pct'] = float(d.get('NetChangePct', 0))
                        PRICE_DATA[sym]['net_chg'] = float(d.get('NetChange', 0))
                        # if sym == "MESM26":
                        #     app.log_msg(f"MESH DATA: {d}")
        
        except Exception as e:
            NEXUS_STATUS = "RECONNECTING"
            app.log_msg(f"Nexus ZMQ Error: {e}. Reconnecting in 5s...")
            await asyncio.sleep(5)
        
        finally:
            sock.close()

# --- ============================== ---
# --- 5. TUI WIDGETS ---
# --- ============================== ---

class HeaderBox(Static):
    time_left = reactive(POLL_MACRO_SECONDS)
    market_status = reactive("ACTIVE [v3.1 MESH]")

    def on_mount(self):
        self.set_interval(POLL_FAST_TICK_SECONDS, self.update_header)
    
    def update_header(self):
        try:
            if self.time_left > 0: self.time_left -= 1

            now = get_ny_time()
            spy = PRICE_DATA[TICKER_EQUITY]
            cur = spy['curr'] or LAST_MACRO_DATA['orats_price']
            
            chg_val = spy['net_chg']
            open_price = cur - chg_val
            display_pct = (chg_val / open_price) * 100 if open_price != 0 else 0.0
            style = "green" if chg_val >= 0 else "red"
            spy_price_str = f"[{style}]${cur:.2f}[/]"
            
            # --- NET PREMIUM FLOW ---
            uw_flow_data = LAST_MACRO_DATA.get('uw_flow', {})
            strike_data = uw_flow_data.get('strike_data', {})
            delta_ticks = uw_flow_data.get('delta_ticks', [])
            
            net_flow_val = 0
            if delta_ticks:
                for tick in delta_ticks:
                    net_flow_val += float(tick.get('net_premium', 0) or 0)
            
            cp = strike_data.get('total_call_premium', 0) or 0
            pp = strike_data.get('total_put_premium', 0) or 0
            net_vol_val = cp - pp
            
            final_val = net_flow_val if abs(net_flow_val) > 1 else net_vol_val
            p_style = "bold green" if final_val > 0 else "bold red"
            
            def fmt_num(val): return f"${val/1e9:.2f}B" if abs(val)>=1e9 else (f"${val/1e6:.1f}M" if abs(val)>=1e6 else f"${val/1e3:.0f}K")
            p_str = fmt_num(final_val)
            if final_val > 0: p_str = "+" + p_str
            flow_str = f"[white]Net Prem: [{p_style}]{p_str}[/]"
            
            atr = LAST_MACRO_DATA['atr']
            rsi = LAST_MACRO_DATA['rsi']
            iv = LAST_MACRO_DATA['iv'] * 100
            ivr = LAST_MACRO_DATA['iv_rank'] * 100 
            
            if rsi >= 70: rsi_str = f"[bold red]RSI:{rsi:.1f}[/]"
            elif rsi <= 30: rsi_str = f"[bold green]RSI:{rsi:.1f}[/]"
            else: rsi_str = f"[white]RSI:{rsi:.1f}[/]"
            
            # Magnet Display
            mag = LAST_MACRO_DATA.get('magnet') or 0
            mag_str = f" | Magnet: [magenta]${mag:.2f}[/]" if mag > 0 else " | Magnet: [dim]WAIT...[/]"
            
            # Divergence Flash
            div_sig = LAST_MACRO_DATA.get('divergence')
            if div_sig:
                rsi_str += f" [bold yellow blink]{div_sig}[/]"

            atr_str = f"[blue]ATR:{atr:.2f}[/]"
            iv_str = f"[gold1]IV:{iv:.1f}% (IVR:{ivr:.0f})[/]"

            status_color = "green" if NEXUS_STATUS == "CONNECTED" else "red"
            nexus_str = f"Nexus: [{status_color}]{NEXUS_STATUS}[/]"
            
            if NEXUS_STATUS == "RECONNECTING":
                nexus_str = f"Nexus: [blink yellow]{NEXUS_STATUS}[/]"

            if self.market_status == "SLEEP":
                countdown_str = f"[white]SLEEPING (Next scan: {self.time_left // 60}m)[/]"
            else:
                countdown_str = f"Scan: [bold yellow]{self.time_left}s[/]"

            # --- IMPLIED FUTURES CALCULATION ---
            implied_str = ""
            if "MESM26" in PRICE_DATA:
                m_data = PRICE_DATA["MESM26"]
                m_curr = m_data.get('curr')
                m_chg = m_data.get('net_chg')
                if m_curr and m_chg is not None:
                    m_open = m_curr - m_chg
                    if m_open > 0:
                        pct_move = m_chg / m_open
                        
                        # Apply to SPY
                        if cur and 0 < open_price: # open_price calculated above
                            implied_spy = open_price * (1 + pct_move)
                            delta_imp = implied_spy - cur
                            i_style = "green" if delta_imp >= 0 else "red"
                            implied_str = f"\n[dim]Futures Implied: ${implied_spy:.2f} ([{i_style}]{delta_imp:+.2f}[/])[/]"

            txt = (
                f" {TICKER_EQUITY}: {spy_price_str} [{style}]{display_pct:+.2f}%[/]  |  {flow_str}  |  "
                f"{iv_str}  |  "
                f"{atr_str}  |  {rsi_str}{mag_str}  |  "
                f"{nexus_str}  |  "
                f"{countdown_str}  |  "
                f"[white]{now.strftime('%H:%M:%S ET')}[/]"
                f"{implied_str}"
            )
            self.update(Text.from_markup(txt))
        except Exception as e:
            # Fallback to simple error header
            self.update(Text.from_markup(f"[bold red]HEADER ERROR: {e}[/]"))

class FlowBox(Static):
    def on_mount(self):
        self.update_content(LAST_MACRO_DATA['uw_flow'])

    def update_content(self, uw_flow_data):
        strike_data = uw_flow_data.get('strike_data', {})
        
        # --- LOGIC: DUAL MODE (Net Flow vs Net Vol) ---
        delta_ticks = uw_flow_data.get('delta_ticks', [])
        
        net_flow_val = 0
        if delta_ticks:
            for tick in delta_ticks:
                net_flow_val += float(tick.get('net_premium', 0) or 0)
            
            current_delta = float(delta_ticks[-1].get('net_delta') or 0)
        else:
            current_delta = 0

        # Fallback Calculation (Call - Put)
        cp = strike_data.get('total_call_premium', 0) or 0
        pp = strike_data.get('total_put_premium', 0) or 0
        net_vol_val = cp - pp
        
        # DECISION LOGIC: Use Flow if data exists, otherwise use Volume
        if abs(net_flow_val) > 1: # Tolerance for float zero
            final_val = net_flow_val
            label_str = "Net Flow (Bull/Bear):"
        else:
            final_val = net_vol_val
            label_str = "Net Prem (Call-Put):"

        # ----------------------------------------------
        
        # Z-Score Display
        z_score = LAST_MACRO_DATA.get('flow_z_score', 0.0)
        z_str = ""
        if z_score > 2.0: z_str = f" [bold green](σ +{z_score:.1f})[/]"
        elif z_score < -2.0: z_str = f" [bold red](σ {z_score:.1f})[/]"
        elif abs(z_score) > 1.0: z_str = f" [white](σ {z_score:.1f})[/]"
        
        top_call_str = "N/A"
        if strike_data.get('top_call_strike'):
            top_call_str = f"${strike_data['top_call_strike']['strike']:g}"
        
        top_put_str = "N/A"
        if strike_data.get('top_put_strike'):
            top_put_str = f"${strike_data['top_put_strike']['strike']:g}"

        t = Table.grid(expand=True, padding=(0, 1))
        t.add_column(); t.add_column(justify="right")
        
        t.add_row(label_str, f"[{'green' if final_val>0 else 'red'}]{fmt_notional(final_val, show_plus=True)}[/]{z_str}")
        t.add_row("Net Delta:", f"[{'green' if current_delta>0 else 'red'}]{fmt_notional(current_delta, show_plus=True)}[/]")
        t.add_row(Text("Call Support", style="bold green"), f"[bold green]{top_call_str}[/]")
        t.add_row(Text("Put Resist", style="bold #FF0000"), f"[bold #FF0000]{top_put_str}[/]")
        
        self.update(Panel(t, title="[bold white]Premium & Delta Flow (ORATS)[/]", border_style="white"))

class WeeklyGexTable(DataTable):
    def on_mount(self):
        self.border_title = "Weekly GEX Structure (ORATS)"
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("Date", "DTE", "Total GEX", "Spot GEX", "Max Pain", "Vol POC", "Flip Pt", "Accel (R)", "Pin (S)", "P/C (Vol)", "P/C (OI)")
        self.update_content(LAST_MACRO_DATA['t_dates'], LAST_MACRO_DATA['gex_summaries'])

    def format_wall(self, wall_data):
        if wall_data is None: return "N/A"
        # Robust check for Series or Dict
        if hasattr(wall_data, 'get'):
             try:
                 val = wall_data.get('strike')
                 if val is not None: return f"${float(val):.0f}"
             except: pass
        return "N/A"

    def update_content(self, dates, gex_summaries):
        self.clear()
        
        if not gex_summaries or len(dates) != len(gex_summaries):
            return

        for i, summary in enumerate(gex_summaries):
            # FILTER: Skip rows with no GEx data (Ghost Expiries)
            gex = summary.get('total_gamma')
            if gex is None:
                continue

            date_str = dates[i].strftime('%Y-%m-%d')
            dte = (dates[i] - get_trading_date()).days
            
            gex_str = fmt_notional(gex)
            gex_style = "green" if (gex or 0) > 0 else "red"

            spot_gex = summary.get('spot_gamma') or 0
            spot_gex_str = fmt_notional(spot_gex)
            spot_gex_style = "green" if spot_gex > 0 else "red"
            
            max_pain_str = f"${summary.get('max_pain_strike'):.0f}" if summary.get('max_pain_strike') else "N/A"
            
            poc_str = "N/A"
            poc_strike = summary.get('volume_poc_strike')
            if poc_strike:
                poc_sent = "C" if summary.get('volume_poc_call_vol', 0) > summary.get('volume_poc_put_vol', 0) else "P"
                poc_style = "green" if poc_sent == 'C' else "red"
                poc_str = Text(f"${poc_strike:.0f} ({poc_sent})", style=poc_style)

            accel_data = summary.get('short_gamma_wall_above')
            accel_style = "red"
            
            # [FIX] Robust check for None/Empty Series
            is_empty = accel_data is None
            if not is_empty and hasattr(accel_data, 'empty'):
                is_empty = accel_data.empty
            
            if is_empty:
                # Fallback to Positive Gamma Resistance
                accel_data = summary.get('long_gamma_wall_above')
                accel_style = "green"
                
            accel_r = self.format_wall(accel_data)
            if accel_r == "N/A": accel_style = "white"

            pin_s = self.format_wall(summary.get('short_gamma_wall_below'))

            flip_pt = summary.get('gex_flip_point')
            flip_str = f"${flip_pt:.0f}" if flip_pt else "N/A"

            pc_oi = summary.get('pc_ratio_oi')
            pc_oi_str = f"{pc_oi:.2f}" if pc_oi is not None else "N/A"
            pc_oi_style = "red" if (pc_oi or 0) > 2.0 else ("green" if (pc_oi or 0) < 0.7 else "white")

            pc_vol = summary.get('pc_ratio_volume')
            pc_vol_str = f"{pc_vol:.2f}" if pc_vol is not None else "N/A"
            pc_vol_style = "red" if (pc_vol or 0) > 0.9 else ("green" if (pc_vol or 0) < 0.7 else "white")

            self.add_row(
                Text(date_str, style="bold" if dte == 0 else "default"),
                str(dte),
                Text(gex_str, style=gex_style),
                Text(spot_gex_str, style=spot_gex_style),
                Text(max_pain_str, style="white"),
                poc_str if isinstance(poc_str, Text) else Text(poc_str, style="yellow"),
                Text(flip_str, style="blue"),
                Text(accel_r, style=accel_style),
                Text(pin_s, style="green"),
                Text(pc_vol_str, style=pc_vol_style),
                Text(pc_oi_str, style=pc_oi_style)
            )

class MktBox(Static):
    def on_mount(self):
        self.set_interval(POLL_FAST_TICK_SECONDS, self.update_market_data)
    
    def update_market_data(self):
        def make_table(ticker_list, title):
             t = Table(box=None, show_header=False, expand=True, padding=(0, 1))
             t.add_column("Symbol", ratio=3)
             t.add_column("Price", justify="right", ratio=4)
             t.add_column("% Chg", justify="right", ratio=3)
             
             for symbol in ticker_list: 
                 data = PRICE_DATA[symbol]
                 curr = data.get('curr')
                 net_chg = data.get('net_chg', 0)
                 style = "green" if net_chg >= 0 else "red"
                 price_str = f"[{style}]${curr:.2f}[/]" if curr else "-"
                 pct_chg_str = "-"
                 if curr and net_chg is not None:
                     open_price = curr - net_chg
                     if open_price != 0:
                         pct_chg = (net_chg / open_price) * 100
                         pct_chg_str = f"[{style}]{pct_chg:+.2f}%[/]"
                     else:
                         pct_chg_str = f"[{style}]0.00%[/]"
                     t.add_row(symbol, price_str, pct_chg_str)
             return Group(Text(title, style="bold underline"), t)

        group = Group(
            make_table(TICKERS_FUTURES, "Futures"),
            Text(" "), 
            make_table(TICKERS_SECTORS, "Sectors")
        )
        self.update(Panel(group, title="[bold white]Broad Market[/]", border_style="white"))

# --- ============================== ---
# --- 6. MAIN TEXTUAL APP ---
# --- ============================== ---

class QuantEngine:
    def __init__(self):
        pass

    def calculate_z_score(self, current_value, history_series):
        """
        Calculates Z-Score using a rolling window of 20 periods.
        Formula: (Current - Mean) / StdDev
        """
        if len(history_series) < 2:
            return 0.0
        
        # Use last 20 items
        window = history_series[-20:]
        mean = np.mean(window)
        std = np.std(window)
        
        if std == 0:
            return 0.0
            
        return (current_value - mean) / std

    def filter_fresh_flow(self, vol, oi):
        """
        Smart Flow Filter:
        - If Volume > Open Interest: Return Volume (High Conviction/Fresh Money)
        - If Volume < Open Interest: Return 0 (Ignore hedging/churn)
        """
        if vol > oi:
            return vol
        return 0

    def check_divergence(self, price_arr, rsi_arr):
        """
        Detects Divergences.
        - Bearish: Price High > Prev High AND RSI High < Prev High
        - Bullish: Price Low < Prev Low AND RSI Low > Prev Low
        """
        if len(price_arr) < 3 or len(rsi_arr) < 3:
            return None
            
        curr_price = price_arr[-1]
        prev_price = price_arr[-2]
        curr_rsi = rsi_arr[-1]
        prev_rsi = rsi_arr[-2]
        
        if curr_price > prev_price and curr_rsi < prev_rsi:
            return "BEAR DIV"
            
        if curr_price < prev_price and curr_rsi > prev_rsi:
            return "BULL DIV"
            
        return None

class MacroDash(App):
    CSS = """
    Screen { layout: vertical; }
    HeaderBox { dock: top; height: 4; background: $surface-darken-1; border-bottom: solid $primary; content-align: center middle; }
    Footer { dock: bottom; height: 1; }
    #log-container { dock: bottom; height: 8; border-top: solid $secondary-darken-2; }
    Log { height: 100%; width: 100%; background: $surface; }
    
    /* MAIN LAYOUT */
    #main-container { width: 100%; height: 1fr; layout: horizontal; }
    
    /* LEFT COLUMN (Small) */
    #left-column { width: 30%; height: 100%; layout: vertical; }
    FlowBox { width: 100%; height: 50%; }
    MktBox { width: 100%; height: 50%; }
    
    /* RIGHT COLUMN (Big) */
    #right-column { width: 70%; height: 100%; }
    WeeklyGexTable { width: 100%; height: 100%; }
    """
    
    quant = QuantEngine()
    flow_history = []
    price_history = [] # For Divergence
    rsi_history = []   # For Divergence
    
    def compose(self) -> ComposeResult:
        yield HeaderBox()
        with Container(id="main-container"):
            # LEFT COLUMN
            with Container(id="left-column"):
                yield FlowBox(id="flow-box")
                yield MktBox()
            
            # RIGHT COLUMN
            with Container(id="right-column"):
                yield WeeklyGexTable(id="gex-weekly")
                
        with Container(id="log-container"):
            yield Log(id="app-log")
        yield Footer()

    def on_mount(self):
        self.log_msg("Starting all background workers...")
        asyncio.create_task(stream_nexus_prices(self))
        # Initial Run
        self.run_macro_fetch()
        
    def run_macro_fetch(self):
        status = is_analysis_time()
        
        sleep_time = 3600 # Default SLEEP
        if status == "ACTIVE": sleep_time = 180
        elif status == "SLOW": sleep_time = 900
        
        self.query_one(HeaderBox).time_left = sleep_time
        self.query_one(HeaderBox).market_status = status
        
        self.log_msg(f"Triggering macro data fetch ({status}). Next scan in {sleep_time}s.")
        self.run_worker(self.fetch_macro_data_sync, exclusive=True, thread=True)
        
        # Schedule next run
        self.set_timer(sleep_time, self.run_macro_fetch)

    def log_msg(self, m: str):
        ts = datetime.datetime.now(ET).strftime('%H:%M:%S')
        # 1. Write to UI
        try: self.query_one(Log).write(f"[{ts}] {m}")
        except: pass
        
        # 2. Write to File (viewer_debug.log)
        try:
            with open("viewer_debug.log", "a") as f:
                f.write(f"[{ts}] {m}\n")
        except: pass

    def update_macro_widgets(self):
        self.log_msg("Updating TUI with new macro data...")
        self.query_one(FlowBox).update_content(LAST_MACRO_DATA['uw_flow'])
        self.query_one(WeeklyGexTable).update_content(LAST_MACRO_DATA['t_dates'], LAST_MACRO_DATA['gex_summaries'])
        self.notify("Macro Data Updated")

    # --- ======================================== ---
    # --- 4. SYNCHRONOUS MACRO DATA METHODS ---
    # --- ======================================== ---

    @work(exclusive=True, thread=True)
    def fetch_macro_data_sync(self):
        global LAST_MACRO_DATA
        self.call_from_thread(self.log_msg, "MACRO: Starting synchronous macro data fetch...")
        
        t_date_today = get_trading_date()
        trading_dates = get_next_n_trading_dates(t_date_today, 14)
        trading_date_strings = [d.strftime('%Y-%m-%d') for d in trading_dates]
        
        atr_val = 0.0
        rsi_val = 0.0
        
        try:
            df_hist = self.get_orats_history_sync(days_back=90)
            if df_hist is not None and not df_hist.empty:
                df_hist['atr'] = calculate_atr(df_hist, period=14)
                df_hist['rsi'] = calculate_rsi(df_hist['close'], period=14)
                latest = df_hist.iloc[-1]
                atr_val = float(latest.get('atr') or 0)
                rsi_val = float(latest.get('rsi') or 0)
                self.call_from_thread(self.log_msg, f"TECH (ORATS): ATR={atr_val:.2f}, RSI={rsi_val:.2f}")
        except Exception as e:
            self.call_from_thread(self.log_msg, f"TECH WARN: Could not calc technicals: {e}")

        new_macro_data = {
            'iv': LAST_MACRO_DATA['iv'],
            'iv_rank': LAST_MACRO_DATA['iv_rank'],
            'skew': LAST_MACRO_DATA['skew'],
            't_dates': trading_dates,
            'gex_summaries': [], 
            'uw_flow': {},
            'orats_price': LAST_MACRO_DATA['orats_price'],
            'atr': atr_val,
            'orats_price': LAST_MACRO_DATA['orats_price'],
            'atr': atr_val,
            'rsi': rsi_val,
            'flow_z_score': LAST_MACRO_DATA.get('flow_z_score', 0.0),
            'divergence': None
        }
        
        # Update History for Divergence
        if new_macro_data['orats_price'] > 0:
            self.price_history.append(new_macro_data['orats_price'])
            self.rsi_history.append(rsi_val)
            # Check Divergence
            div = self.quant.check_divergence(self.price_history, self.rsi_history)
            if div: new_macro_data['divergence'] = div

        try:
            orats_summary_data = self.get_orats_data_sync('summaries')
            orats_strikes_data = self.get_orats_data_sync('strikes')
            
            # [FIX] Generate mock UW strikes data from ORATS for Dash back-compat
            uw_strikes_data = []
            uw_delta_data = {}
            if orats_strikes_data:
                for item in orats_strikes_data:
                    try:
                        c_vol = float(item.get('callVolume', 0))
                        c_oi = float(item.get('callOpenInterest', 0))
                        p_vol = float(item.get('putVolume', 0))
                        p_oi = float(item.get('putOpenInterest', 0))
                        
                        # estimate premium from bid/ask (midprice)
                        c_mid = (float(item.get('callBidPrice', 0)) + float(item.get('callAskPrice', 0))) / 2
                        p_mid = (float(item.get('putBidPrice', 0)) + float(item.get('putAskPrice', 0))) / 2
                        if c_mid == 0 and float(item.get('callBid', 0)) > 0: c_mid = (float(item.get('callBid', 0)) + float(item.get('callAsk', 0))) / 2
                        if p_mid == 0 and float(item.get('putBid', 0)) > 0: p_mid = (float(item.get('putBid', 0)) + float(item.get('putAsk', 0))) / 2

                        c_prem = c_vol * c_mid * 100
                        p_prem = p_vol * p_mid * 100
                        
                        uw_strikes_data.append({
                            'strike': float(item.get('strike', 0)),
                            'call_volume': c_vol,
                            'call_open_interest': c_oi,
                            'call_premium': c_prem,
                            'put_volume': p_vol,
                            'put_open_interest': p_oi,
                            'put_premium': p_prem,
                            'expiry': item.get('expirDate')
                        })
                    except: pass

            if orats_summary_data:
                d = orats_summary_data[0] if isinstance(orats_summary_data, list) else orats_summary_data
                new_macro_data['iv'] = float(d.get('iv30d') or 0)
                new_macro_data['iv_rank'] = float(d.get('ivPctile1m') or 0)
                new_macro_data['skew'] = float(d.get('rSlp30') or 0)
                new_macro_data['orats_price'] = float(d.get('stockPrice') or d.get('last') or 0)
            
            spy_price = PRICE_DATA[TICKER_EQUITY]['curr'] or new_macro_data['orats_price']
            
            if not spy_price or spy_price == 0:
                self.call_from_thread(self.log_msg, "MACRO: Aborting analysis, no valid SPY price.")
                return

            if orats_strikes_data:
                gex_summaries = []
                for date_str in trading_date_strings:
                    _, gex_summary = self.analyze_gamma_exposure(orats_strikes_data, spy_price, date_str)
                    gex_summaries.append(gex_summary)
                new_macro_data['gex_summaries'] = gex_summaries
                
                # [NEW] Accumulated Premium Tracker Injection 
                # Placed inside `orats_strikes_data` block so it only runs if valid options chain exists
                cum_net_prem, cum_net_delta = track_accumulated_premium(orats_strikes_data, spy_price, "viewer_premium_state.json")
                uw_delta_data = {'data': [{'net_premium': cum_net_prem, 'net_delta': cum_net_delta}]}

            new_macro_data['uw_flow']['delta_ticks'] = uw_delta_data.get('data', []) if uw_delta_data else []
            new_macro_data['uw_flow']['strike_data'] = self.process_uw_strike_data(uw_strikes_data)
            
            LAST_MACRO_DATA = new_macro_data
            
            # --- ANTIGRAVITY STATE DUMP (DASH METRICS) ---
            try:
                current_state = {
                    "atr": new_macro_data.get('atr', 0.0),
                    "rsi": new_macro_data.get('rsi', 0.0),
                    "flow_z_score": new_macro_data.get('flow_z_score', 0.0),
                    "divergence": new_macro_data.get('divergence'),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                antigravity_dump("nexus_dash_metrics.json", current_state)
                
                # --- ANTIGRAVITY STATE DUMP (SPY PROFILE) ---
                # This feeds the Bridge with the "Headline" numbers
                try:
                    # 1. Get GEX Data (Default to 0 if list empty)
                    gex_summary = new_macro_data.get('gex_summaries', [{}])[0]
                    net_gamma = gex_summary.get('total_gamma', 0)
                    
                    # 2. Get Walls (Handle Pandas Series or Dicts safely)
                    def get_strike(obj):
                        if obj is None: return 0
                        # Handle Pandas Series or Dict
                        if hasattr(obj, 'get'): return float(obj.get('strike', 0))
                        # Handle direct attribute if applicable (unlikely here but safe)
                        return 0

                    call_wall = get_strike(gex_summary.get('short_gamma_wall_above'))
                    put_wall = get_strike(gex_summary.get('long_gamma_wall_below'))

                    # 3. Sanitize GEX Structure for JSON
                    clean_gex_structure = []
                    for g in new_macro_data.get('gex_summaries', []):
                        clean_item = g.copy()
                        # Convert Pandas Series to simple dicts or scalars
                        for key in ['short_gamma_wall_above', 'short_gamma_wall_below', 'long_gamma_wall_above', 'long_gamma_wall_below']:
                            val = clean_item.get(key)
                            if val is not None:
                                if hasattr(val, 'to_dict'):
                                    clean_item[key] = val.to_dict()
                                elif hasattr(val, 'item'):
                                     clean_item[key] = val.item()
                        clean_gex_structure.append(clean_item)

                    # 4. Dump to 'nexus_spy_profile.json'
                    curr_price = PRICE_DATA[TICKER_EQUITY]['curr'] or new_macro_data.get('orats_price') or 0
                    
                    # Capture Magnet (Volume POC)
                    magnet_level = gex_summary.get('volume_poc_strike') or 0
                    # Pass into context for display
                    new_macro_data['magnet'] = magnet_level
                    
                    # [NEW] Gather UW Flow for Streamlit
                    uw_flow_data = new_macro_data.get('uw_flow', {})
                    delta_ticks = uw_flow_data.get('delta_ticks', [])
                    net_flow_val = 0
                    current_delta = 0
                    if delta_ticks:
                        for tick in delta_ticks:
                            net_flow_val += float(tick.get('net_premium', 0) or 0)
                        current_delta = float(delta_ticks[-1].get('net_delta') or 0)
                        
                    # [NEW] Gather Futures Implied
                    implied_spy = 0
                    if "MESM26" in PRICE_DATA:
                        m_data = PRICE_DATA["MESM26"]
                        m_curr = m_data.get('curr')
                        m_chg = m_data.get('net_chg')
                        if m_curr and m_chg is not None:
                            m_open = m_curr - m_chg
                            if m_open > 0:
                                pct_move = m_chg / m_open
                                if curr_price > 0: implied_spy = curr_price * (1 + pct_move)

                    # Force dump even if price is 0 (we need the GEX)
                    spy_state = {
                        "script": "viewer_dash",
                        "current_price": curr_price,
                        "net_gex": net_gamma,
                        "call_wall": call_wall,
                        "put_wall": put_wall,
                        "magnet": magnet_level,
                        "zero_gamma": gex_summary.get('gex_flip_point', 0),
                        "net_premium": net_flow_val,    # Added for Streamlit Header
                        "net_delta": current_delta,     # Added for Streamlit Header
                        "futures_implied": implied_spy, # Added for Streamlit Header
                        "gex_structure": clean_gex_structure,
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    antigravity_dump("nexus_spy_profile.json", spy_state)
                    # print(f"✅ [DATA] SPY GEX Dumped: {fmt_notional(net_gamma)}") 
                    
                    # [NEW] Native HTTP Post to Supabase (Bypassing SDK Int64 limits)
                    try:
                        import os
                        import requests
                        import json
                        
                        SUPABASE_URL = os.getenv('SUPABASE_URL')
                        SUPABASE_KEY = os.getenv('SUPABASE_KEY')
                        
                        if SUPABASE_URL and SUPABASE_KEY:
                            with open("nexus_spy_profile.json", "r") as f:
                                native_spy_state = json.load(f)
                                
                            payload = {
                                "id": "spy_latest",
                                "data": native_spy_state
                            }
                            
                            headers = {
                                "apikey": SUPABASE_KEY,
                                "Authorization": f"Bearer {SUPABASE_KEY}",
                                "Content-Type": "application/json",
                                "Prefer": "resolution=merge-duplicates"
                            }
                            
                            url = f"{SUPABASE_URL}/rest/v1/nexus_profile"
                            resp = requests.post(url, json=payload, headers=headers, timeout=5)
                            # self.call_from_thread(self.log_msg, f"SUPABASE HTTP POST: {resp.status_code}")
                    except Exception as e:
                        self.call_from_thread(self.log_msg, f"SUPABASE HTTP ERROR: {e}")
                except Exception as e:
                    self.call_from_thread(self.log_msg, f"BRIDGE DUMP ERROR: {e}")
                
            except Exception as e:
                self.call_from_thread(self.log_msg, f"State Dump Err: {e}")

            self.call_from_thread(self.log_msg, "MACRO: Data refresh complete.")
            self.call_from_thread(self.update_macro_widgets)
            
            # --- SAVE SNAPSHOTS FOR ANALYZE_SNAPSHOTS.PY ---
            try:
                self.save_snapshot_data(orats_strikes_data, uw_strikes_data, spy_price)
            except Exception as e:
                self.call_from_thread(self.log_msg, f"SNAPSHOT SAVE ERROR: {e}")

        except Exception as e:
            self.call_from_thread(self.log_msg, f"MACRO CRITICAL: {e}")
            self.call_from_thread(self.log_msg, traceback.format_exc())

    def save_snapshot_data(self, orats_strikes, uw_strikes, current_price):
        """
        Saves fetched data as CSV snapshots for analyze_snapshots.py
        """
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        
        # --- 1. SPY SNAPSHOT (ORATS) ---
        if orats_strikes:
            spy_rows = []
            for item in orats_strikes:
                # ORATS returns wide format: "callVolume", "putVolume", etc.
                # We need long format for analyze_snapshots.py
                
                base_data = {
                    'symbol': 'SPY',
                    'exp': item.get('expirDate'),
                    'dte': item.get('dte'),
                    'stk': item.get('strike'),
                    'underlying_price': current_price
                }
                
                c_row = base_data.copy()
                c_row.update({
                    'type': 'CALL',
                    'vol': item.get('callVolume', 0),
                    'oi': item.get('callOpenInterest', 0),
                    'delta': float(item.get('callDelta') or item.get('delta') or 0),
                    'gamma': float(item.get('callGamma') or item.get('gamma') or 0),
                    'theta': float(item.get('callTheta') or item.get('theta') or 0),
                    'vega': float(item.get('callVega') or item.get('vega') or 0),
                    'prem': 0 # Placeholder if premium not directly available
                })
                # Estimate Premium if Bid/Ask available
                try:
                    mid = (item.get('callBidPrice', 0) + item.get('callAskPrice', 0)) / 2
                    if mid == 0: mid = (item.get('callBid', 0) + item.get('callAsk', 0)) / 2
                    c_row['prem'] = mid * c_row['vol'] * 100
                except: pass
                spy_rows.append(c_row)
                
                p_row = base_data.copy()
                
                # Put Delta inferred if missing
                c_delta = float(item.get('callDelta') or item.get('delta') or 0)
                p_delta = float(item.get('putDelta') or 0)
                if p_delta == 0 and c_delta != 0: 
                    p_delta = c_delta - 1.0

                p_row.update({
                    'type': 'PUT',
                    'vol': item.get('putVolume', 0),
                    'oi': item.get('putOpenInterest', 0),
                    'delta': p_delta,
                    'gamma': float(item.get('putGamma') or item.get('gamma') or 0),
                    'theta': float(item.get('putTheta') or item.get('theta') or 0),
                    'vega': float(item.get('putVega') or item.get('vega') or 0),
                    'prem': 0
                })
                try:
                    mid = (item.get('putBidPrice', 0) + item.get('putAskPrice', 0)) / 2
                    if mid == 0: mid = (item.get('putBid', 0) + item.get('putAsk', 0)) / 2
                    p_row['prem'] = mid * p_row['vol'] * 100
                except: pass
                spy_rows.append(p_row)
            
            if spy_rows:
                df_spy = pd.DataFrame(spy_rows)
                os.makedirs("snapshots_spy", exist_ok=True)
                df_spy.to_csv(f"snapshots_spy/spy_snapshot_{timestamp}.csv", index=False)
                self.call_from_thread(self.log_msg, f"Saved SPY Snapshot: {len(df_spy)} rows")

        # --- 2. SWEEPS SNAPSHOT (UW) ---
        if uw_strikes:
            # UW 'flow-per-strike' is aggregated.
            # analyze_snapshots 'sweeps' expects individual trades usually, but we can adapt.
            # Columns: ticker, parsed_expiry, parsed_strike, parsed_type, total_premium, total_size
            
            uw_rows = []
            for item in uw_strikes:
                # Call Row
                if item.get('call_volume', 0) > 0:
                    uw_rows.append({
                        'ticker': TICKER_EQUITY,
                        'parsed_expiry': item.get('expiry'),
                        'parsed_strike': item.get('strike'),
                        'parsed_type': 'CALL',
                        'total_premium': item.get('call_premium', 0),
                        'total_size': item.get('call_volume', 0),
                        'open_interest': 0 
                    })
                
                # Put Row
                if item.get('put_volume', 0) > 0:
                    uw_rows.append({
                        'ticker': TICKER_EQUITY,
                        'parsed_expiry': item.get('expiry'),
                        'parsed_strike': item.get('strike'),
                        'parsed_type': 'PUT',
                        'total_premium': item.get('put_premium', 0),
                        'total_size': item.get('put_volume', 0),
                        'open_interest': 0
                    })
            
            if uw_rows:
                df_uw = pd.DataFrame(uw_rows)
                os.makedirs("snapshots_sweeps", exist_ok=True)
                df_uw.to_csv(f"snapshots_sweeps/uw_flow_snapshot_{timestamp}.csv", index=False)
                self.call_from_thread(self.log_msg, f"Saved UW Snapshot: {len(df_uw)} rows")

    @api_retry
    def get_orats_data_sync(self, endpoint_type):
        api_url = f"https://api.orats.io/datav2/live/{endpoint_type}"
        params = {'token': ORATS_API_KEY.strip(), 'ticker': TICKER_EQUITY, 'fields': 'ticker,expirDate,strike,delta,gamma,theta,vega,callDelta,putDelta,callGamma,putGamma,callTheta,putTheta,callVega,putVega,callVolume,putVolume,callOpenInterest,putOpenInterest,callBidPrice,callAskPrice,putBidPrice,putAskPrice'}
        try:
            response = requests.get(api_url, params=params, timeout=15)
            if response.status_code == 429:
                self.call_from_thread(self.log_msg, f"ORATS Rate Limit Hit ({endpoint_type}) - waiting...")
                time.sleep(60) 
                return None
            response.raise_for_status()
            data = response.json()
            result_data = data.get('data', data)
            if result_data == [] or result_data == {}: return None
            return result_data if result_data else None
        except Exception as e:
            self.call_from_thread(self.log_msg, f"ORATS Error ({endpoint_type}): {e}")
            return None

    def process_uw_strike_data(self, data):
        results = {
            "top_call_strike": None, "top_put_strike": None,
            "total_call_premium": 0, "total_put_premium": 0
        }
        if not isinstance(data, list): return results
        
        processed_strikes = []
        total_call_prem = 0
        total_put_prem = 0
        
        for strike_data in data:
            try:
                # SMART FLOW FILTER
                c_vol = float(strike_data.get('call_volume', 0) or 0)
                c_oi = float(strike_data.get('call_open_interest', 0) or 0)
                p_vol = float(strike_data.get('put_volume', 0) or 0)
                p_oi = float(strike_data.get('put_open_interest', 0) or 0)
                
                # Only count volume if it is "Fresh" (Vol > OI)
                # Note: We apply this logic to the PREMIUM calculation if possible.
                # But here we only have premium totals. 
                # Approximation: If Vol > OI, keep the premium. Else 0.
                
                call_prem = float(strike_data.get('call_premium', 0) or 0)
                put_prem = float(strike_data.get('put_premium', 0) or 0)
                
                # Near-Term Filter: Only track Support/Resistance strikes within 7 Days (Ignore LEAPS)
                try:
                    exp = strike_data.get('expiry')
                    if exp:
                        exp_date = datetime.datetime.strptime(exp, '%Y-%m-%d').date()
                        dte = (exp_date - get_trading_date()).days
                        if dte > 7:
                            continue
                except: pass

                processed_strikes.append({
                    "strike": float(strike_data.get('strike')),
                    "call_premium": call_prem, "put_premium": put_prem
                })
                total_call_prem += call_prem
                total_put_prem += put_prem
            except Exception:
                continue
        
        if processed_strikes:
            results["top_call_strike"] = max(processed_strikes, key=lambda x: x['call_premium'])
            results["top_put_strike"] = max(processed_strikes, key=lambda x: x['put_premium'])
        
        results["total_call_premium"] = total_call_prem
        results["total_put_premium"] = total_put_prem
        
        # Calculate Net Flow for Z-Score
        net_flow = total_call_prem - total_put_prem
        self.flow_history.append(net_flow)
        
        # Calculate Z-Score
        z = self.quant.calculate_z_score(net_flow, self.flow_history)
        LAST_MACRO_DATA['flow_z_score'] = z
        
        return results

    def analyze_gamma_exposure(self, strikes_data, spy_price, target_date):
        summary_stats = {
            'date': target_date, # [FIX] Inject Date for JSON consumers
            'total_gamma': None, 'spot_gamma': None, 
            'max_pain_strike': None, 'volume_poc_strike': None,
            'volume_poc_total_vol': 0, 'volume_poc_call_vol': 0, 'volume_poc_put_vol': 0,
            'short_gamma_wall_above': None, 'short_gamma_wall_below': None,
            'long_gamma_wall_above': None, 'long_gamma_wall_below': None,
            'total_call_volume': 0, 'total_put_volume': 0,
            'total_call_oi': 0, 'total_put_oi': 0,
            'total_call_oi': 0, 'total_put_oi': 0,
            'pc_ratio_volume': None, 'pc_ratio_oi': None,
            'gex_flip_point': None
        }
        if not isinstance(strikes_data, list) or not strikes_data or not spy_price or not target_date:
            return None, summary_stats
        try:
            df = pd.DataFrame(strikes_data)
            required_cols = ['expirDate', 'strike', 'gamma', 'callOpenInterest', 'putOpenInterest', 'callVolume', 'putVolume']
            if any(col not in df.columns for col in required_cols):
                return None, summary_stats

            df_target = df[df['expirDate'] == target_date].copy()
            if df_target.empty: return None, summary_stats

            for col in required_cols[1:]:
                 df_target[col] = pd.to_numeric(df_target[col], errors='coerce')
            df_target.fillna(0, inplace=True)
            df_target.sort_values('strike', inplace=True) # Ensure sorted for Flip Logic

            call_gex = df_target['callOpenInterest'] * 100 * df_target['gamma']
            put_gex = (df_target['putOpenInterest'] * 100 * df_target['gamma'])
            # [ALIGNMENT] Match SPX 'gex_worker_nexus.py' Logic (Netting)
            # Was: (call + put) * -1 (Gross Short)
            # Now: (call - put) (Net Imbalance)
            total_gex = (call_gex - put_gex) 
            df_target['total_gamma_exp'] = total_gex * (spy_price**2) * 0.01
            summary_stats['total_gamma'] = df_target['total_gamma_exp'].sum()

            df_target['distance_to_spot'] = abs(df_target['strike'] - spy_price)
            near_atm = df_target[df_target['distance_to_spot'] <= (spy_price * 0.02)]
            summary_stats['spot_gamma'] = near_atm['total_gamma_exp'].sum()

            # --- GAMMA FLIP LOGIC (LOCAL ZERO CROSSING) ---
            # Match Profiler Logic: Find where GEX sign flips locally
            df_sorted = df_target.sort_values('strike')
            strikes = df_sorted['strike'].values
            gammas = df_sorted['total_gamma_exp'].values
            
            best_flip = None
            for i in range(len(strikes) - 1):
                g1 = gammas[i]; g2 = gammas[i+1]
                if (g1 > 0 and g2 < 0) or (g1 < 0 and g2 > 0):
                    if abs(g1) < abs(g2): flip = strikes[i]
                    else: flip = strikes[i+1]
                    
                    # Check Distance (5% Filter)
                    if abs(flip - spy_price) < (spy_price * 0.05):
                        best_flip = float(flip)
                        break # Take the first valid flip found (usually closest if sorted)
            
                
            # [FIX] Calculate Acceleration (GEX Velocity)
            # Use Gamma Notional at Flip Point as proxy, or Total Gamma / 1B
            if best_flip:
                flip_idx = np.where(strikes == best_flip)[0]
                if len(flip_idx) > 0:
                    summary_stats['gex_velocity'] = gammas[flip_idx[0]] # Raw GEX at flip
            
            # Fallback
            if 'gex_velocity' not in summary_stats and summary_stats['total_gamma'] != 0:
                summary_stats['gex_velocity'] = summary_stats['total_gamma'] / 1e9

            summary_stats['gex_flip_point'] = best_flip
            # ------------------------

            sig_gex_df = df_target[df_target['total_gamma_exp'].abs() > 1e-6].copy()
            if not sig_gex_df.empty:
                short_gex = sig_gex_df[sig_gex_df['total_gamma_exp'] < 0]
                if not short_gex.empty:
                    above_s = short_gex[short_gex['strike'] > spy_price]; below_s = short_gex[short_gex['strike'] < spy_price]
                    # Use largest MAGNITUDE (idxmin because values are negative)
                    if not above_s.empty: summary_stats['short_gamma_wall_above'] = above_s.loc[above_s['total_gamma_exp'].idxmin()]
                    if not below_s.empty: summary_stats['short_gamma_wall_below'] = below_s.loc[below_s['total_gamma_exp'].idxmin()]
                
                long_gex = sig_gex_df[sig_gex_df['total_gamma_exp'] > 0]
                if not long_gex.empty:
                    above_l = long_gex[long_gex['strike'] > spy_price]; below_l = long_gex[long_gex['strike'] < spy_price]
                    # Use largest MAGNITUDE (idxmax because values are positive)
                    if not above_l.empty: summary_stats['long_gamma_wall_above'] = above_l.loc[above_l['total_gamma_exp'].idxmax()]
                    if not below_l.empty: summary_stats['long_gamma_wall_below'] = below_l.loc[below_l['total_gamma_exp'].idxmax()]

            strikes = df_target['strike'].unique()
            if strikes.size > 0 and (df_target['callOpenInterest'].sum() > 0 or df_target['putOpenInterest'].sum() > 0):
                total_values = []
                for expiry_price in strikes:
                     if pd.isna(expiry_price): continue
                     call_val = (expiry_price - df_target['strike']).clip(lower=0) * df_target['callOpenInterest']
                     put_val = (df_target['strike'] - expiry_price).clip(lower=0) * df_target['putOpenInterest']
                     total_values.append((expiry_price, call_val.sum() + put_val.sum()))
                if total_values:
                    summary_stats['max_pain_strike'] = min(total_values, key=lambda x: x[1])[0]

            df_target['total_volume'] = df_target['callVolume'] + df_target['putVolume']
            if not df_target.empty and df_target['total_volume'].sum() > 0:
                # [ALIGNMENT] Match SPX Profiler Logic (Raw Volume POC)
                # Was: Notional Volume (Vol * Strike). 
                # Now: Raw Volume (Call + Put) to identically match SPX logic.
                poc_row = df_target.loc[df_target['total_volume'].idxmax()]
                
                summary_stats['volume_poc_strike'] = poc_row['strike']
                summary_stats['volume_poc_total_vol'] = poc_row['total_volume']
                summary_stats['volume_poc_call_vol'] = poc_row['callVolume']
                summary_stats['volume_poc_put_vol'] = poc_row['putVolume']
                
            total_call_vol = df_target['callVolume'].sum()
            total_put_vol = df_target['putVolume'].sum()
            total_call_oi = df_target['callOpenInterest'].sum()
            total_put_oi = df_target['putOpenInterest'].sum()

            summary_stats.update({
                'total_call_volume': total_call_vol, 'total_put_volume': total_put_vol,
                'total_call_oi': total_call_oi, 'total_put_oi': total_put_oi
            })
            
            if total_call_vol > 0: summary_stats['pc_ratio_volume'] = total_put_vol / total_call_vol
            if total_call_oi > 0: summary_stats['pc_ratio_oi'] = total_put_oi / total_call_oi

            return df_target, summary_stats
        except Exception as e:
            self.call_from_thread(self.log_msg, f"GEX Analysis Error: {e}")
            return None, summary_stats

    def get_orats_history_sync(self, days_back=100):
        end_date = datetime.datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        
        api_url = "https://api.orats.io/datav2/hist/dailies"
        params = {
            'token': ORATS_API_KEY.strip(),
            'ticker': TICKER_EQUITY,
            'tradeDate': f'{start_date},{end_date}'
        }
        
        try:
            response = requests.get(api_url, params=params, timeout=15)
            if response.status_code == 429:
                 self.call_from_thread(self.log_msg, "ORATS History Rate Limit. Skipping technicals.")
                 return None
            response.raise_for_status()
            data = response.json()
            raw_data = data.get('data', [])
            
            if not raw_data: return None
            
            df = pd.DataFrame(raw_data)
            df.columns = df.columns.str.lower()
            
            df['close'] = pd.to_numeric(df['clspx'], errors='coerce')
            df['high'] = pd.to_numeric(df['hipx'], errors='coerce')
            df['low'] = pd.to_numeric(df['lopx'], errors='coerce')
            df['open'] = pd.to_numeric(df['open'], errors='coerce')
            
            df['tradedate'] = pd.to_datetime(df['tradedate'])
            df.sort_values('tradedate', ascending=True, inplace=True)
            
            return df if len(df) >= 15 else None
            
        except Exception as e:
            self.call_from_thread(self.log_msg, f"ORATS History Error: {e}")
            return None

if __name__ == "__main__":
    MacroDash().run()