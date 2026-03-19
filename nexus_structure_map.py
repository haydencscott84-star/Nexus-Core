import os
"""
Nexus-Powered STRUCTURAL MAP (Sidecar - Profiler Style Conversion)
- ROLE: Secondary Dashboard (Runs alongside Whale Hunter)
- CONVERSION: Matches 'SPX Profiler' logic (Strike - Basis)/10
- VISUALS: Clean Text, Spy Equivalent on ALL SPX rows
"""

# --- Core Python ---
import asyncio, datetime, os, json, ssl, sys, re, time
from datetime import timedelta
from collections import deque

# --- Third-Party ---
try:
    import zmq, zmq.asyncio, pytz, requests
    ET = pytz.timezone('US/Eastern')
    UTC = pytz.utc
except ImportError:
    sys.exit("Missing deps. Run: pip install pyzmq pytz requests textual")

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Log, TabbedContent, TabPane
from textual.containers import Vertical, Container
from rich.text import Text
from textual import work
from textual.reactive import reactive
from textual import on

# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))

# Ports for Sidecar Operation (Non-Conflicting)
ZMQ_PORT = 5560         
ZMQ_SELECT_PORT = 5561  
ZMQ_TOPIC = "flow-alerts-structure"
ZMQ_SELECT_TOPIC = b"SELECT_STRUCTURE"

TICKERS_TO_SHOW = ["SPY", "SPX", "SPXW"]

# --- THRESHOLDS ---
PREMIUM_THRESHOLDS = {
    "SPY": 1_000_000,   
    "SPX": 5_000_000,   
    "SPXW": 5_000_000,
    "DEFAULT": 500_000
}

POLL_FAST_TICK_SECONDS = 10.0
LIVE_SWEEPS_MAXLEN = 5000
MIN_DTE = 0; MAX_DTE = 60; SHORT_DTE_CUTOFF = 3

# --- GLOBAL STATE ---
LIVE_SWEEPS = deque(maxlen=LIVE_SWEEPS_MAXLEN)
ZMQ_STATUS = "WAITING..."
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
MARKET_LEVELS_FILE = os.path.join(SCRIPT_DIR, "market_levels.json")
MARKET_STRUCTURE = {"spy_price": 0.0, "spx_price": 0.0, "current_basis": 0.0}

# Price Freshness Tracking
PRICE_TIMESTAMPS = {"SPY": 0.0, "SPX": 0.0}

# --- HELPERS ---
CHAIN_REGEX = re.compile(r"^(?P<ticker>.+?)(?P<expiry>\d{6})(?P<type>[CP])(?P<strike_int>\d{5})(?P<strike_dec>\d{3})$")

def parse_option_chain(chain_symbol: str):
    if not chain_symbol: return None, None, None
    match = CHAIN_REGEX.match(chain_symbol)
    if not match: return ("Idx", "N/A", "N/A") if chain_symbol.startswith("$") else (None, None, None)
    d = match.groupdict()
    expiry = f"20{d['expiry'][:2]}-{d['expiry'][2:4]}-{d['expiry'][4:]}"
    otype = "CALL" if d['type'] == 'C' else "PUT"
    strike = float(f"{int(d['strike_int'])}.{d['strike_dec']}")
    return expiry, otype, strike

def get_ny_time(): return datetime.datetime.now(ET)
def get_trading_date(): 
    d = get_ny_time().date()
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d

def fmt_notional(value, show_plus=False):
    if value is None: return "N/A"
    v = abs(value)
    s = f"${v/1e9:.2f}B" if v>=1e9 else (f"${v/1e6:.1f}M" if v>=1e6 else (f"${v/1e3:.1f}K" if v>=1e3 else f"${v:.0f}"))
    if value < 0: s = "-" + s
    elif value > 0 and show_plus: s = "+" + s
    elif value == 0: return "$0"
    return s

def score_sweep(s_data: dict, market: dict, sentiment: str) -> tuple[int, list]:
    score = 0; notes = []
    try:
        prem = s_data.get('total_premium', 0); dte = s_data.get('parsed_dte', -1)
        strike = s_data.get('parsed_strike', 0); otype = s_data.get('parsed_type', 'N/A')
        spy_px = market.get("spy_price", 0)

        if dte >= 30: score += 2; notes.append("SWING")
        if prem >= 100_000_000: score += 5; notes.append("MEGA WALL")
        elif prem >= 10_000_000: score += 3; notes.append("MAJOR WALL")
        elif prem >= 1_000_000: score += 1; notes.append("WALL")

        is_otm = (otype == 'CALL' and strike > spy_px) or (otype == 'PUT' and strike < spy_px)
        if is_otm: score += 1; notes.append("OTM")
    except Exception as e: notes.append(f"Err: {e}")
    return score, notes

# --- MAIN APP ---
class NexusStructureMap(App):
    CSS = """
    Screen { layout: vertical; }
    HeaderBox { dock: top; height: 4; background: $surface-darken-1; border-bottom: solid $primary; content-align: center middle; }
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

    class HeaderBox(Static):
        def on_mount(self): self.set_interval(5.0, self.update_header)
        def update_header(self):
            now = get_ny_time()
            stats = {
                "SPY": {"bull": 0.0, "bear": 0.0}, "SPX": {"bull": 0.0, "bear": 0.0},
                "D0":  {"bull": 0.0, "bear": 0.0}, "D1":  {"bull": 0.0, "bear": 0.0},
                "TOTAL": {"bull": 0.0, "bear": 0.0}
            }
            
            for s in list(LIVE_SWEEPS):
                prem = s.get('total_premium', 0)
                sent = s.get('sentiment_str', 'MID')
                otype = s.get('parsed_type', 'N/A')
                tkr = s.get('ticker', '')
                dte = s.get('parsed_dte', -1)
                is_bull = (sent == "BUY" and otype == "CALL") or (sent == "SELL" and otype == "PUT")
                bkt = "bull" if is_bull else "bear"
                if "SPX" in tkr: stats['SPX'][bkt] += prem
                else: stats['SPY'][bkt] += prem
                if dte <= SHORT_DTE_CUTOFF: stats['D0'][bkt] += prem
                else: stats['D1'][bkt] += prem
                stats['TOTAL'][bkt] += prem

            c = lambda v: "green" if v>=0 else "red"
            spy_n = stats['SPY']['bull'] - stats['SPY']['bear']
            spx_n = stats['SPX']['bull'] - stats['SPX']['bear']
            tot_n = stats['TOTAL']['bull'] - stats['TOTAL']['bear']
            
            basis = MARKET_STRUCTURE.get('current_basis', 0.0)
            basis_txt = f"[bold white]Basis:[/] [cyan]{basis:+.2f}[/]"
            
            l1 = f" [bold blue]NEXUS STRUCTURAL MAP[/] | {now.strftime('%H:%M:%S ET')} | {basis_txt}"
            l2 = (f" SPY Walls: [{c(spy_n)}]{fmt_notional(spy_n,True)}[/] | SPX Walls: [{c(spx_n)}]{fmt_notional(spx_n,True)}[/] | TOT Walls: [{c(tot_n)}]{fmt_notional(tot_n,True)}[/]")
            self.update(Text.from_markup(f"{l1}\n{l2}"))

    class SweepTable(DataTable):
        sweeps_on_display = []
        last_data_signature = ""
        def __init__(self, dte_mode="ALL", **kwargs):
            super().__init__(**kwargs); self.dte_mode = dte_mode
        def on_mount(self):
            self.add_columns("Prio", "Time", "Tkr", "Exp", "DTE", "Strike (SPY)", "Type", "Side", "Daily Prem", "Vol @ Price", "Notes")
            self.cursor_type = "row"; self.set_interval(2.0, self.update_table)
        
        def update_table(self):
            if not LIVE_SWEEPS: return
            sig = f"{len(LIVE_SWEEPS)}_{LIVE_SWEEPS[0]['total_premium']}_{self.dte_mode}"
            if sig == self.last_data_signature: return
            self.last_data_signature = sig

            cutoff = SHORT_DTE_CUTOFF; to_show = []
            for s in list(LIVE_SWEEPS):
                d = s.get('parsed_dte', -1)
                if self.dte_mode == "SHORT" and d <= cutoff: to_show.append(s)
                elif self.dte_mode == "LONG" and d > cutoff: to_show.append(s)
                elif self.dte_mode == "ALL": to_show.append(s)
            
            to_show.sort(key=lambda s: float(s.get('total_premium', 0)), reverse=True)
            
            self.sweeps_on_display = to_show
            saved_row = self.cursor_coordinate.row
            self.clear()
            
            for i, s in enumerate(to_show):
                try:
                    ts_val = s.get('executed_at') or 0
                    if ts_val > 0:
                        dt_obj = datetime.datetime.fromtimestamp(ts_val, tz=ET)
                        tm = dt_obj.strftime("%H:%M:%S")
                    else: tm = "Day Sum"
                except: tm = "Day Sum"
                
                otype = s.get('parsed_type', 'N/A'); ost = "green" if otype=='CALL' else "red"
                sent = s.get('sentiment_str', 'MID'); sst = "green" if sent=='BUY' else ("red" if sent=='SELL' else "white")
                sc = s.get('priority_score', 0); scst = "bold yellow" if sc>=5 else ("white" if sc>0 else "dim")
                stk = s.get('parsed_strike', 0); 
                
                # --- PROFILER STYLE CONVERSION ---
                # Formula: (Strike - Basis) / 10
                # Fallback: Strike / 10 (if Basis is 0/missing)
                basis = MARKET_STRUCTURE.get('current_basis', 0.0)
                
                if "SPX" in s.get('ticker', ''):
                    if abs(basis) > 0.1:
                        spy_equiv = (stk - basis) / 10
                        stk_s = f"${stk:,.0f} ({spy_equiv:.1f})"
                    else:
                        # Fallback just like Profiler line 277
                        spy_equiv = stk / 10
                        stk_s = f"${stk:,.0f} ({spy_equiv:.0f})"
                else:
                    stk_s = f"${stk:,.2f}".replace(".00", "")
                
                prem = s.get('total_premium', 0)
                prem_style = "bold " + sst
                if prem > 50_000_000: prem_style = "bold magenta"
                
                self.add_row(Text(str(sc), style=scst), tm, s.get('ticker'), s.get('parsed_expiry',''), str(s.get('parsed_dte','')),
                             stk_s, Text(otype, style=ost), Text(sent, style=sst),
                             Text(fmt_notional(prem), style=prem_style),
                             f"{s.get('total_size')} @ ${s.get('price')}", Text(s.get('priority_notes',''), style="dim italic"), key=str(i))
            
            if saved_row > 0 and saved_row < self.row_count: self.move_cursor(row=saved_row, animate=False)

    def compose(self) -> ComposeResult:
        yield self.HeaderBox()
        with Container(id="main-view"):
            with TabbedContent(initial="d0"):
                with TabPane(f"0-{SHORT_DTE_CUTOFF} DTE", id="d0"): yield self.SweepTable(id="t0", dte_mode="SHORT")
                with TabPane(f"{SHORT_DTE_CUTOFF}+ DTE", id="d1"): yield self.SweepTable(id="t1", dte_mode="LONG")
        with Container(id="log-container"): yield Log(id="app-log")
        yield Footer()

    async def on_ready(self):
        self.log_msg("Init Structure Map (Profiler Mode)..."); 
        self.update_market_structure()
        self.poll_screener_loop()
        try:
            self.select_sock = self.zmq_ctx.socket(zmq.PUB); self.select_sock.bind(f"tcp://127.0.0.1:{ZMQ_SELECT_PORT}")
            self.log_msg(f"✅ Ready. Publishing to {ZMQ_SELECT_PORT}")
        except Exception as e: self.log_msg(f"Select Sock Fail: {e}")

    @work(thread=True)
    def poll_screener_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        url = "https://api.unusualwhales.com/api/screener/option-contracts"
        headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        
        while True:
            for t in TICKERS_TO_SHOW:
                try:
                    th = PREMIUM_THRESHOLDS.get(t, 500_000)
                    p = {'ticker_symbol':t, 'order':'premium', 'order_direction':'desc', 'limit':30, 'min_dte':MIN_DTE, 'max_dte':MAX_DTE, 'min_premium':th}
                    r = requests.get(url, headers=headers, params=p, timeout=5)
                    if r.status_code == 200:
                        d = r.json().get('data', [])
                        for i in reversed(d): self.process_screener_row(t, i)
                except Exception as e: pass
            time.sleep(POLL_FAST_TICK_SECONDS)

    def process_screener_row(self, t, i):
        global PRICE_TIMESTAMPS, MARKET_STRUCTURE
        try:
            prem = float(i.get('premium') or 0)
            chain = i.get('option_symbol')
            ts = i.get('last_trade_time') or i.get('timestamp') or i.get('date')
            ts_val = 0
            if ts:
                 try:
                    if isinstance(ts, str): ts_val = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
                    elif isinstance(ts, (int,float)): ts_val = ts/1000 if ts > 10000000000 else ts
                 except: pass

            px = float(i.get('close') or (float(i.get('bid') or 0)+float(i.get('ask') or 0))/2)
            av = float(i.get('ask_side_volume') or 0); bv = float(i.get('bid_side_volume') or 0)
            
            # --- PRECISION BASIS LOGIC (FROM PROFILER) ---
            # Find the freshest price in the batch to set the global basis
            spot = float(i.get('underlying_price') or 0)
            if spot > 0:
                key = "SPX" if "SPX" in t else "SPY"
                if ts_val >= PRICE_TIMESTAMPS.get(key, 0):
                    if key == "SPY": MARKET_STRUCTURE['spy_price'] = spot
                    elif key == "SPX": MARKET_STRUCTURE['spx_price'] = spot
                    PRICE_TIMESTAMPS[key] = ts_val
            
            m = {
                'ticker':t, 'total_premium': prem, 
                'option_chain': chain, 'executed_at': ts_val,
                'total_size': int(i.get('volume') or 0), 'price': px,
                'underlying_price': spot,
                'total_ask_side_prem': av*px*100, 'total_bid_side_prem': bv*px*100
            }
            
            found = False
            for existing in LIVE_SWEEPS:
                if existing['option_chain'] == chain:
                    existing.update(m)
                    self.process_logic(existing)
                    found = True
                    break
            
            if not found:
                self.process_logic(m)
                LIVE_SWEEPS.appendleft(m)
                
        except Exception as e: pass

    def process_logic(self, d):
        chain = d.get('option_chain'); exp, otype, stk = parse_option_chain(chain)
        if not all([exp, otype, stk]): return
        dte = (datetime.date.fromisoformat(exp) - get_trading_date()).days
        d.update({'parsed_expiry':exp, 'parsed_type':otype, 'parsed_strike':stk, 'parsed_dte':dte})
        
        ap = d.get('total_ask_side_prem', 0); bp = d.get('total_bid_side_prem', 0)
        sent = "BUY" if ap > bp else ("SELL" if bp > ap else "MID"); d['sentiment_str'] = sent
        sc, n = score_sweep(d, MARKET_STRUCTURE, sent)
        d['priority_score'] = sc; d['priority_notes'] = ", ".join(n)

    @work(thread=True)
    def update_market_structure(self):
        global MARKET_STRUCTURE
        while True:
            try:
                spy=MARKET_STRUCTURE.get('spy_price',0); spx=MARKET_STRUCTURE.get('spx_price',0)
                if spy>0 and spx>0: MARKET_STRUCTURE['current_basis'] = spx-(spy*10)
                if os.path.exists(MARKET_LEVELS_FILE):
                    with open(MARKET_LEVELS_FILE,'r') as f: MARKET_STRUCTURE.update(json.load(f))
            except: pass
            time.sleep(1)

    def log_msg(self, m): self.query_one(Log).write(f"[{datetime.datetime.now(ET).strftime('%H:%M:%S')}] {m}")

if __name__ == "__main__": NexusStructureMap().run()