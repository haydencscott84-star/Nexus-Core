import os
# FILE: nexus_hunter.py
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Input, Button, Label, Select, RichLog
from textual.containers import Container, Horizontal, Vertical
from textual import on
import asyncio, aiohttp, json, os, signal, sys, zmq, zmq.asyncio
import pandas as pd
from datetime import datetime

# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
ZMQ_PORT = 5580 # Dedicated Hunter Port

# --- LENIENCY PROTOCOL ---
class LeniencyEngine:
    def __init__(self, min_delta=0.30):
        self.min_delta = min_delta

    def score(self, c):
        score = 100.0
        
        # 1. Delta Threshold (Range Filter)
        d = abs(c.get('greeks', {}).get('delta') or 0.0)
        
        if d < self.min_delta:
            # Below minimum delta -> Penalty
            # RELAXED: Penalty reduced from 500x to 200x
            score -= (self.min_delta - d) * 200 
            # RELAXED: Kill threshold increased from 0.10 to 0.20
            if d < (self.min_delta - 0.20): score = 0 
        else:
            # Above minimum -> No Penalty (Valid Range)
            # Optional: Slight penalty for Deep ITM if we want to stay near money?
            # User said "greatest theoretical value", so let's trust Edge.
            pass
        
        # 2. Spread Penalty (Liquidity)
        bid = float(c.get('bid') or 0); ask = float(c.get('ask') or 0)
        if ask > 0:
            spread = (ask - bid) / ask
            # RELAXED: Thresholds doubled (10% -> 20%, 5% -> 10%)
            if spread > 0.20: score -= 50 # Kill score if spread > 20%
            elif spread > 0.10: score -= 20
            
        # 3. Edge Bonus (Value) - PRIMARY DRIVER
        edge = c.get('edge', 0)
        # Boost weight: 5% edge was +10, now make it +25 (5x multiplier)
        score += edge * 5 
        
        return max(0, round(score, 1))

# --- APP ---
class NexusHunter(App):
    CSS = """
    Screen { layout: vertical; }
    
    /* Top Control Bar */
    #controls { 
        height: 5; 
        dock: top; 
        background: $surface-darken-1; 
        padding: 1; 
        align-vertical: middle;
        layout: horizontal;
    }

    /* Group Containers */
    .group {
        layout: horizontal;
        height: 100%;
        align-vertical: middle;
        margin-right: 3; /* Spacing between groups */
        border-right: solid $primary-darken-3; /* Visual separator */
        padding-right: 1;
    }
    .group-last {
        layout: horizontal;
        height: 100%;
        align-vertical: middle;
        border: none;
    }

    /* Labels */
    Label { 
        margin-right: 1; 
        content-align: right middle; 
        height: 3; 
        text-style: bold;
        color: $text-muted;
    }

    /* Inputs */
    .ctrl_sm { width: 8; height: 3; background: $surface; border: none; }
    .ctrl_md { width: 14; height: 3; background: $surface; border: none; }
    
    /* Select */
    Select { width: 14; height: 3; }

    /* Button */
    #btn_hunt { margin-left: 2; height: 3; min-width: 12; }
    
    /* Status */
    #status_lbl { margin-left: 2; content-align: left middle; height: 3; color: $text-muted; }

    /* Results Table */
    #results { height: 1fr; border-top: solid $primary; }
    .score_high { color: $success; text-style: bold; }
    .score_med { color: $warning; }
    .score_low { color: $error; }

    /* Log Window */
    #log_win {
        height: 8;
        dock: bottom;
        border-top: solid $secondary;
        background: $surface;
        color: $text-muted;
        overflow-y: scroll;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal(id="controls"):
            # GROUP 1: DELTA
            with Container(classes="group"):
                yield Label("Min Delta:")
                yield Input(value="0.30", id="in_delta", classes="ctrl_sm")
            
            # GROUP 2: DTE
            with Container(classes="group"):
                yield Label("DTE:")
                yield Input(value="7", id="in_min_dte", classes="ctrl_sm")
                yield Label("-", classes="lbl-sep")
                yield Input(value="45", id="in_max_dte", classes="ctrl_sm")
            
            # GROUP 3: TYPE
            with Container(classes="group"):
                yield Label("Type:")
                yield Select.from_values(["CALL", "PUT"], value="CALL", id="sel_type", allow_blank=False)
            
            # GROUP 4: ACTION
            with Container(classes="group-last"):
                yield Button("HUNT", id="btn_hunt", variant="primary")
                yield Button("SEND TO DASH", id="btn_send", variant="default", disabled=True)
                yield Static("IDLE", id="status_lbl")
            
        yield DataTable(id="results")
        yield RichLog(id="log_win", wrap=True, highlight=True, markup=True)
        yield Footer()

    async def on_mount(self):
        # 1. ZMQ Health Check Bind
        self.zmq_ctx = zmq.asyncio.Context()
        self.pub_sock = self.zmq_ctx.socket(zmq.PUB)
        self.pub_sock.bind(f"tcp://*:5580")
        
        # 2. Setup Table
        dt = self.query_one("#results", DataTable)
        dt.cursor_type = "row"
        # 2. Setup Table
        dt = self.query_one("#results", DataTable)
        dt.cursor_type = "row"
        dt.add_columns("EXPIRY", "DTE", "CONTRACT", "PREMIUM", "VOL", "OI", "V/OI", "MKT($)", "THEO($)", "EDGE", "CONFIDENCE", "BE($)", "WIN%")
        
        # 3. Heartbeat Loop
        asyncio.create_task(self.heartbeat())
        self.hunt_results = {} # Store raw data keyed by RowKey
        self.log_msg("Nexus Hunter Initialized.")
        
        # [FIX] Auto-Run Hunt on Startup for immediate visibility
        self.call_after_refresh(self.run_hunt)

    def log_msg(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.query_one("#log_win", RichLog).write(f"[{ts}] {msg}")

    async def heartbeat(self):
        while True:
            # Broadcast "ALIVE" to Launch Sequence
            try:
                self.pub_sock.send_multipart([b"HEARTBEAT", b"HUNTER_OK"])
            except: pass
            await asyncio.sleep(5)

    @on(Button.Pressed, "#btn_hunt")
    async def run_hunt(self):
        try:
            target_delta = float(self.query_one("#in_delta", Input).value)
            min_dte = int(self.query_one("#in_min_dte", Input).value)
            max_dte = int(self.query_one("#in_max_dte", Input).value)
            target_type = str(self.query_one("#sel_type", Select).value)
        except ValueError:
            self.query_one("#status_lbl").update("INVALID INPUT")
            self.log_msg("[bold red]INVALID INPUT:[/ bold red] Check numeric fields.")
            return

        self.query_one("#status_lbl").update("HUNTING...")
        self.log_msg(f"Starting Hunt: {target_type} | Delta: {target_delta} | DTE: {min_dte}-{max_dte}")
        
        # 1. FETCH UW CANDIDATES (The Funnel)
        # Using SPY for demo, normally would scan list
        async with aiohttp.ClientSession() as sess:
            # A. Get Chain from UW
            url = f"https://api.unusualwhales.com/api/screener/option-contracts"
            params = {'ticker_symbol': 'SPY', 'min_volume': 100, 'min_dte': min_dte, 'max_dte': max_dte}
            headers = {'Authorization': f'Bearer {UW_API_KEY}'}
            
            try:
                async with sess.get(url, params=params, headers=headers, timeout=10) as r:
                    if r.status != 200:
                        self.query_one("#status_lbl").update(f"UW ERROR: {r.status}")
                        self.log_msg(f"[bold red]UW API Error:[/ bold red] {r.status}")
                        return
                    uw_data = (await r.json()).get('data', [])
                    self.log_msg(f"UW Data Fetched: {len(uw_data)} contracts.")
            except Exception as e:
                self.query_one("#status_lbl").update("UW FAIL")
                self.log_msg(f"[bold red]UW Exception:[/ bold red] {e}")
                return

            # B. Get ORATS Fair Value
            o_url = "https://api.orats.io/datav2/live/strikes"
            try:
                async with sess.get(o_url, params={'token': ORATS_API_KEY, 'ticker': 'SPY'}, timeout=10) as r:
                    if r.status != 200:
                        self.query_one("#status_lbl").update(f"ORATS ERROR: {r.status}")
                        self.log_msg(f"[bold red]ORATS API Error:[/ bold red] {r.status}")
                        return
                    orats_data = (await r.json()).get('data', [])
                    self.log_msg(f"ORATS Data Fetched: {len(orats_data)} strikes.")
            except Exception as e:
                self.query_one("#status_lbl").update("ORATS FAIL")
                self.log_msg(f"[bold red]ORATS Exception:[/ bold red] {e}")
                return
                
            # C. Map ORATS SMV
            # Map: "Exp|Strike|Type" -> SMV
            theo_map = {}
            for o in orats_data:
                try:
                    exp = o['expirDate']
                    stk = float(o['strike'])
                    
                    # CALL
                    key_c = f"{exp}|{stk:.1f}|C"
                    theo_map[key_c] = float(o.get('callValue') or 0)
                    
                    # PUT
                    key_p = f"{exp}|{stk:.1f}|P"
                    theo_map[key_p] = float(o.get('putValue') or 0)
                except: continue

            # 2. SCORE & CALCULATE EDGE
            engine = LeniencyEngine(target_delta)
            results = []
            
            for c in uw_data:
                # PARSE OPTION SYMBOL: SPY251219P00400000
                # Format: Ticker + YYMMDD + Type + Strike(8 digits)
                try:
                    sym = c.get('option_symbol', '')
                    if len(sym) < 15: continue
                    
                    # Extract parts
                    # Ticker is everything before the last 15 chars
                    # But we know it's SPY, so let's just parse the suffix
                    suffix = sym[-15:]
                    date_str = suffix[:6] # 251219
                    type_char = suffix[6] # P or C
                    strike_str = suffix[7:] # 00400000
                    
                    # Convert Date: YYMMDD -> YYYY-MM-DD
                    # 251219 -> 2025-12-19
                    exp = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
                    
                    # Convert Strike
                    stk = float(strike_str) / 1000.0
                    
                    # Type
                    c_type = 'CALL' if type_char == 'C' else 'PUT'
                    
                except Exception as e:
                    continue

                # Filter by Type
                if c_type != target_type: continue

                # ORATS uses 'C'/'P'
                o_type_code = 'C' if c_type == 'CALL' else 'P'
                key = f"{exp}|{stk:.1f}|{o_type_code}"
                
                theo = theo_map.get(key, 0)
                
                # PRICE: API seems to return 'close' but not bid/ask in screener
                mkt = float(c.get('close') or 0)
                
                edge = 0
                if theo > 0 and mkt > 0:
                    edge = ((theo - mkt) / theo) * 100
                
                # GREEKS: Top level in this endpoint
                # Inject into structure expected by LeniencyEngine if needed, 
                # or update LeniencyEngine. But easier to just map it here.
                # LeniencyEngine expects c.get('greeks', {}).get('delta')
                # Let's patch 'c' to match that structure or update 'c'
                c['greeks'] = {
                    'delta': float(c.get('delta') or 0),
                    'gamma': float(c.get('gamma') or 0),
                    'theta': float(c.get('theta') or 0),
                    'vega': float(c.get('vega') or 0)
                }
                # Also add parsed fields for display
                c['exp'] = exp
                c['stk'] = stk
                c['type'] = c_type
                c['bid'] = 0 # Not available in screener
                c['ask'] = 0 # Not available in screener
                
                c['edge'] = edge
                score = engine.score(c)
                
                if score > 50: # Minimum viability filter
                    results.append((score, c, mkt, theo, edge))

            # 3. RENDER
            results.sort(key=lambda x: x[0], reverse=True)
            dt = self.query_one("#results", DataTable)
            dt.clear()
            self.hunt_results.clear()
            
            if not results:
                self.query_one("#status_lbl").update("NO MATCHES")
                self.log_msg("[yellow]No matches found matching criteria.[/yellow]")
                return
            
            for score, c, mkt, theo, edge in results[:20]:
                style = "score_high" if score > 80 else "score_med"
                
                # Calculations
                # DTE
                try:
                    d_obj = datetime.strptime(c['exp'], "%Y-%m-%d")
                    dte = (d_obj - datetime.now()).days
                except: dte = 0
                
                # Contract Name
                contract = f"{c['ticker_symbol']} {c['stk']:.1f} {c['type'][0]}"
                
                # Premium (Total Traded Premium = Vol * Price * 100)
                # Or just use the 'premium' field from API if valid, else calc
                prem = float(c.get('premium') or (c.get('volume',0) * mkt * 100))
                
                # Vol/OI
                vol = int(c.get('volume', 0))
                oi = int(c.get('open_interest', 0))
                voi = vol / oi if oi > 0 else 0.0
                
                # P/C Ratio (Not available in this endpoint, use placeholder or N/A)
                pc_ratio = "-"
                
                # Confidence (Score based)
                conf = "HIGH" if score > 80 else ("MED" if score > 50 else "LOW")
                conf_style = "bold green" if score > 80 else ("bold yellow" if score > 50 else "dim red")
                
                # Break Even
                be = c['stk'] + mkt if c['type'] == 'CALL' else c['stk'] - mkt
                
                # Win % (Delta Proxy)
                delta = abs(c['greeks']['delta'])
                win_pct = f"{delta*100:.0f}%"
                
                # Color Coding
                edge_color = "green" if edge > 0 else "red"
                edge_txt = f"[{edge_color}]{edge:+.1f}%[/]"
                
                # Premium Formatting
                # Premium Formatting
                if prem >= 1_000_000:
                    prem_txt = f"${prem/1_000_000:.1f}M"
                else:
                    prem_txt = f"${prem/1_000:.1f}K"
                

                
                # Store Raw Data for Selection
                # add_row returns the RowKey
                # But wait, add_row returns the key? Textual docs say yes.
                # Actually, let's just use the key we generate or get.
                # dt.add_row returns the key.
                
                # Let's capture the key.
                # We need to do this carefully. 
                # Since we are iterating, we can't easily capture the return value in this big block.
                # I will split the add_row call.
                
                key = dt.add_row(
                    c['exp'], 
                    str(dte), 
                    contract, 
                    prem_txt, 
                    str(vol), 
                    str(oi), 
                    f"{voi:.1f}x", 
                    f"${mkt:.2f}", 
                    f"${theo:.2f}", 
                    edge_txt, 
                    f"[{conf_style}]{conf}[/]", 
                    f"${be:.2f}", 
                    win_pct
                )
                
                # Enrich 'c' with calculated fields for the dashboard
                c['mkt'] = mkt
                c['dte'] = dte
                c['desc'] = contract
                c['volume'] = vol
                c['open_interest'] = oi
                
                self.hunt_results[key] = c
                
        self.query_one("#status_lbl").update("DONE")
        self.query_one("#status_lbl").update("DONE")
        self.log_msg(f"[green]Hunt Complete. Found {len(results)} candidates.[/green]")

    @on(DataTable.RowSelected, "#results")
    def on_row_selected(self, event):
        # 1. Get Row Data
        row_key = event.row_key
        row = self.query_one("#results", DataTable).get_row(row_key)
        
        # Row Format: EXPIRY, DTE, CONTRACT, PREMIUM, VOL, OI, V/OI, MKT($), THEO($), EDGE, CONFIDENCE, BE($), WIN%
        # Indices:    0       1    2         3        4    5   6     7       8        9     10          11     12
        
        try:
            if row_key in self.hunt_results:
                self.selected_contract = self.hunt_results[row_key]
                self.log_msg(f"Selected (Rich Data): {self.selected_contract['desc']}")
            else:
                # Fallback (Should not happen)
                self.log_msg("[red]Error: Raw data not found for row.[/red]")
                return
            
            # Enable Send Button
            btn = self.query_one("#btn_send")
            btn.disabled = False
            btn.variant = "warning"
            self.log_msg(f"Selected: {self.selected_contract['desc']}")
            
        except Exception as e:
            self.log_msg(f"[red]Selection Error: {e}[/red]")

    @on(Button.Pressed, "#btn_send")
    async def send_to_dash(self):
        if not hasattr(self, 'selected_contract'): return
        
        c = self.selected_contract
        
        # Construct Payload expected by Trader Dashboard
        # Dashboard expects: {'symbol': 'SPY', 'stk': 400.0, 'dte': 7, 'type': 'CALL', 'mkt': 1.23}
        # Note: 'symbol' in Dash usually means the full option symbol or just ticker?
        # Looking at Dash code: `xp.sym=d.get('symbol')` -> `watch_sym`.
        # Dash `fmt_row` uses `stk`, `type`, `prem`.
        # Let's send a robust payload.
        
        payload = {
            "symbol": c.get('symbol') or c.get('ticker_symbol'), # SPY
            "stk": c['stk'],
            "type": c['type'],
            "exp": c['exp'],
            "mkt": c['mkt'],
            "dte": c.get('dte', 0),
            "vol": int(c.get('volume', 0)),
            "oi": int(c.get('open_interest', 0)),
            "delta": c.get('greeks', {}).get('delta', 0),
            "gamma": c.get('greeks', {}).get('gamma', 0),
            "theta": c.get('greeks', {}).get('theta', 0),
            "vega": c.get('greeks', {}).get('vega', 0),
            "iv": c.get('implied_volatility', 0),
            "occ_sym": c.get('option_symbol'),
            "source": "HUNTER"
        }
        
        try:
            # Publish SELECT message
            self.pub_sock.send_multipart([b"SELECT", json.dumps(payload).encode('utf-8')])
            
            self.log_msg(f"[bold green]SENT TO DASH:[/ bold green] {c['desc']}")
            self.query_one("#btn_send").variant = "success"
            self.query_one("#btn_send").label = "SENT!"
            
            # Reset button after delay
            await asyncio.sleep(1)
            self.query_one("#btn_send").variant = "warning"
            self.query_one("#btn_send").label = "SEND TO DASH"
            
        except Exception as e:
            self.log_msg(f"[red]Send Failed: {e}[/red]")

if __name__ == "__main__":
    # KILL SWITCH INTEGRATION
    def signal_handler(sig, frame):
        sys.exit(0)
    signal.signal(signal.SIGINT, signal_handler)
    
    app = NexusHunter()
    app.run()
