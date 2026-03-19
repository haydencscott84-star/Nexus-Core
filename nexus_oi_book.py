
import asyncio
import datetime
import os
import json
import math
import time
import re
from datetime import timedelta
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, DataTable, TabbedContent, TabPane, Button, Label, Switch
from textual.containers import Vertical, Horizontal, Container
from textual.reactive import reactive
from rich.text import Text
from textual import work, on
import aiohttp
import numpy as np
from dotenv import load_dotenv

# --- CONFIG ---
load_dotenv()
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"
POLL_SECONDS = 600 # 10 Minutes (Deep Scan)
DEBUG_MODE = False

def log_debug(msg):
    with open("oi_debug.log", "a") as f:
        f.write(f"[{datetime.datetime.now()}] {msg}\n")

# --- BUCKETS ---
BUCKETS = {
    "short": (0, 3),
    "med": (4, 30),
    "long": (31, 1000)
}

import zoneinfo

def get_trading_date():
    tz = zoneinfo.ZoneInfo("America/New_York")
    now = datetime.datetime.now(tz)
    return now.date()

class NexusOIOrderBook(App):
    CSS = """
    Screen { layout: vertical; }
    Header { dock: top; }
    DataTable { height: 1fr; border: solid green; }
    #header_stats { text-align: center; background: $accent; color: auto; padding: 1; }
    """
    
    current_spot = reactive(0.0)
    current_iv30 = reactive(0.0)
    implied_move = reactive(0.0)
    next_update = reactive(0.0) # Timestamp for next update
    
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Initializing 10-Day Focused Scan...", id="header_stats")
        yield DataTable(id="dt_main")
        yield Button("Force Refresh (Run Scan)", id="btn_refresh", variant="primary")
        yield Footer()

    async def on_mount(self):
        log_debug("App Mounted")
        self.base_stat_text = "Initializing Scan..."
        self.market_status = "Checking..."
        self.session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=50)) # Higher limit for nuclear scan
        
        # Setup Table
        log_debug("Setting up Table...")
        dt = self.query_one("#dt_main", DataTable)
        dt.add_columns("Put Side (OI)", "Strike", "Call Side (OI)")
        dt.cursor_type = "row"
            
        # Worker starts automatically when called
        log_debug("Starting Workers (Asyncio)...")
        asyncio.create_task(self.refresh_loop())
        asyncio.create_task(self.timer_loop())
        log_debug("Workers Started.")

    @on(Button.Pressed, "#btn_refresh")
    def on_refresh(self):
        self.query_one("#header_stats", Static).update("Force Refresh Initiated...")
        # Reset timer
        self.next_update = time.time()  # Trigger immediate
        self.refresh_loop()

    async def timer_loop(self):
        log_debug("Timer Loop Started")
        while True:
            try:
                now = time.time()
                if self.next_update > now:
                    remain = int(self.next_update - now)
                    # We can't update the whole header string easily without re-constructing it
                    # So we relies on the header_stats update in fetch_and_render
                await asyncio.sleep(1)
            except Exception as e:
                log_debug(f"Timer Loop Error: {e}")
                await asyncio.sleep(1)

    async def refresh_loop(self):
        log_debug("Refresh Loop Started (Asyncio)")
        # Initial short delay to let UI paint
        await asyncio.sleep(1)
        while True:
            try:
                log_debug("Starting Fetch Cycle...")
                await self.fetch_context()
                await self.fetch_and_render()
                log_debug("Fetch Cycle Complete.")
                
                # Smart Polling Logic
                # [FIX] Timezone Awareness (Using zoneinfo)
                tz = zoneinfo.ZoneInfo("America/New_York")
                est_now = datetime.datetime.now(tz).replace(tzinfo=None)
                # Market: 9:00 AM - 5:00 PM EST (Broad window)
                is_market = (est_now.weekday() < 5 and (9 <= est_now.hour < 17)) or DEBUG_MODE
                
                # Dynamic Interval
                current_interval = 600 # Fixed 10m for deep scan stability
                
                self.market_status = f"MKT {'OPEN' if is_market else 'CLOSED'}"
                # self.last_stat_text = ... (Deprecated, handled by timer)
                
                # Set Next Update Time
                self.next_update = time.time() + current_interval
                
                # Countdown Loop
                st = time.time()
                while time.time() < self.next_update:
                     # Check for force refresh or app exit
                     if self.app._exit or self.next_update < time.time(): break
                     
                     self.update_header_timer()
                     await asyncio.sleep(1)
                    
            except Exception as e:
                log_debug(f"Loop Error: {e}")
                await asyncio.sleep(5) # Error backoff
            
            # If we exited loop due to force refresh or timeout, we loop back immediately
            
    def update_header_timer(self):
        remain = max(0, int(self.next_update - time.time()))
        
        if not hasattr(self, 'base_stat_text'): return
        
        self.query_one("#header_stats", Static).update(
            f"{self.base_stat_text} | {self.market_status} | Next: {remain}s"
        )

    async def fetch_context(self):
        # Fetch Spot & IV30 from ORATS (Reliable)
        url = "https://api.orats.io/datav2/live/summaries"
        params = {'token': ORATS_API_KEY, 'ticker': TICKER}
        try:
            async with self.session.get(url, params=params, timeout=10) as r:
                if r.status == 200:
                    data = (await r.json()).get('data', [{}])[0]
                    self.current_spot = float(data.get('stockPrice', 0))
                    self.current_iv30 = float(data.get('iv30d', 0))
                    
                    # Calculate Implied Move (30 Day)
                    # Range = Spot * IV * sqrt(30/365)
                    if self.current_spot > 0 and self.current_iv30 > 0:
                        self.implied_move = self.current_spot * self.current_iv30 * math.sqrt(30.0 / 365.0)
        except: pass

    async def fetch_contracts_deep(self, min_dte, max_dte):
        log_debug(f"ORATS Scan: {min_dte}-{max_dte}d")
        if self.current_spot == 0: return []
        
        url = "https://api.orats.io/datav2/live/strikes"
        params = {'token': ORATS_API_KEY.strip(), 'ticker': TICKER}
        
        self.query_one("#header_stats", Static).update("Scanning Data from ORATS...")
        try:
            async with self.session.get(url, params=params, timeout=15) as r:
                if r.status == 200:
                    raw_data = (await r.json()).get('data', [])
                    data = []
                    today = get_trading_date()
                    
                    for item in raw_data:
                        exp_str = item.get('expirDate')
                        if not exp_str: continue
                        
                        try:
                            exp_date = datetime.datetime.strptime(exp_str, '%Y-%m-%d').date()
                            dte = (exp_date - today).days
                        except: continue
                        
                        if min_dte <= dte <= max_dte:
                            stk = float(item.get('strike', 0))
                            
                            tpad = TICKER.ljust(6, ' ')
                            dstr = exp_date.strftime('%y%m%d')
                            sstr = f"{int(stk * 1000):08d}"
                            
                            sym_call = f"{tpad}{dstr}C{sstr}"
                            sym_put = f"{tpad}{dstr}P{sstr}"
                            
                            data.append({
                                'option_symbol': sym_call,
                                'strike': stk,
                                'option_type': 'call',
                                'volume': item.get('callVolume', 0),
                                'open_interest': item.get('callOpenInterest', 0),
                                'prev_oi': item.get('callOpenInterest', 0) # Net 0
                            })
                            data.append({
                                'option_symbol': sym_put,
                                'strike': stk,
                                'option_type': 'put',
                                'volume': item.get('putVolume', 0),
                                'open_interest': item.get('putOpenInterest', 0),
                                'prev_oi': item.get('putOpenInterest', 0) # Net 0
                            })
                    return data
        except Exception as e:
            log_debug(f"ORATS Fetch Error: {e}")
        return []

    async def fetch_and_render(self):
        self.query_one("#header_stats", Static).update("Scanning Next 10 Days...")
        
        # Fetch 0-10 DTE Full Chains
        data = await self.fetch_contracts_deep(0, 10)
        
        total_recs = len(data)
        
        # Range Info
        im_txt = f"+/-${self.implied_move:.1f}" if self.implied_move > 0 else "N/A"
        legend = " | FMT: Total [Vol] | (Green=Calls, Red=Puts)"
        base_text = f"Contracts: {total_recs} | Spot: ${self.current_spot:.2f} | IV30: {self.current_iv30:.1%} | Range: {im_txt}{legend}"
        self.base_stat_text = base_text
        self.update_header_timer()
        
        self.render_bucket("main", data)

    def render_bucket(self, tid, data):
        dt = self.query_one(f"#dt_{tid}", DataTable)
        dt.clear()
        
        if not data: return

        agg = {} 
        
        # Filter Range (Implied Move)
        # User requested wider view ("missing data")
        min_strike = 0; max_strike = 9999
        if self.current_spot > 0 and self.implied_move > 0:
            min_strike = self.current_spot - (self.implied_move * 1.5) # [FIX] User requested 1.5x
            max_strike = self.current_spot + (self.implied_move * 1.5)
        elif self.current_spot > 0:
            # Fallback if no IV (12%)
            min_strike = self.current_spot * 0.88
            max_strike = self.current_spot * 1.12
            
        for c in data:
            try:
                sym = c.get('option_symbol')
                stk = float(c.get('strike') or 0)
                
                # [FIX] Robust Strike Parsing from OSI if API returns 0
                if stk == 0 and len(sym) >= 15:
                    try:
                        # OSI Last 8 chars are strike * 1000
                        stk_str = sym[-8:]
                        stk = float(stk_str) / 1000.0
                    except: pass

                if stk == 0: continue
                
                # --- FILTER ---
                if stk < min_strike or stk > max_strike:
                    continue
                
                # [FIX] Robust Parsing (Standard OSI)
                # Type char is at index -9
                type_char = 'P'
                if len(sym) >= 15:
                     qt = sym[-9]
                     if qt in ['C', 'P']: type_char = qt
                
                if stk not in agg: agg[stk] = {'P': {'oi':0, 'chg':0, 'vol':0}, 'C': {'oi':0, 'chg':0, 'vol':0}}
                
                oi = int(c.get('open_interest', 0))
                prev = int(c.get('prev_oi', 0))
                vol = int(c.get('volume', 0))
                chg = oi - prev
                
                agg[stk][type_char]['oi'] += oi
                agg[stk][type_char]['chg'] += chg
                agg[stk][type_char]['vol'] += vol
            except Exception as e:
                log_debug(f"Row Error: {e}")
                continue
            
        strikes = sorted(agg.keys())
        log_debug(f"Bucket {tid}: Found {len(strikes)} unique strikes.")
        if not strikes: return
        
        # Calc Max
        local_max = 1
        for s in strikes:
            local_max = max(local_max, agg[s]['P']['oi'], agg[s]['C']['oi'])
            
        for s in strikes:
            row = agg[s]
            p_render = self.get_bar_text(row['P'], local_max, align='right', opt_type='P')
            
            s_style = "white"
            if self.current_spot > 0 and abs(s - self.current_spot) < (self.current_spot * 0.005):
                s_style = "bold yellow reverse"
            elif self.current_spot > 0 and abs(s - self.current_spot) < (self.current_spot * 0.02):
                s_style = "bold yellow"
                
            s_render = Text(f"{s:.0f}", style=s_style)
            c_render = self.get_bar_text(row['C'], local_max, align='left', opt_type='C')
            dt.add_row(p_render, s_render, c_render)
            
        # --- SUPABASE PILE ---
        if tid == "main":
            try:
                payload = {
                    "spot": self.current_spot,
                    "iv30": self.current_iv30,
                    "implied_move": self.implied_move,
                    "strikes": strikes,
                    "agg": {str(s): agg[s] for s in strikes},
                    "updated_at": time.time()
                }
                asyncio.create_task(self.push_to_supabase(payload))
            except Exception as e:
                log_debug(f"Supabase Payload Error: {e}")
                
    async def push_to_supabase(self, payload):
        supa_url = os.getenv("SUPABASE_URL")
        supa_key = os.getenv("SUPABASE_KEY")
        if not supa_url or not supa_key: return
        
        url = f"{supa_url}/rest/v1/nexus_profile"
        headers = {
            "apikey": supa_key,
            "Authorization": f"Bearer {supa_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates"
        }
        data = {
            "id": "oi_book",
            "data": payload
        }
        try:
            async with self.session.post(url, json=data, headers=headers, timeout=5) as r:
                if r.status in [200, 201]:
                    log_debug("Successfully pushed OI Book state to Supabase.")
                else:
                    log_debug(f"Supabase push failed: HTTP {r.status}")
        except Exception as e:
            log_debug(f"Supabase exception: {e}")

    def get_bar_text(self, data, max_val, align='left', opt_type='C'):
        val = data['oi']
        vol = data['vol']
        width = 40
        bar_len = int((val / max_val) * width) if max_val > 0 else 0
        
        style = "bold green" if opt_type == 'C' else "bold red"
        
        bar_char = "█"
        bar_str = bar_char * bar_len
        
        # Format: 10.0k [V:2.0k]
        lbl = f"{val/1000:.1f}k [V:{vol/1000:.1f}k]"
        
        if align == 'right':
            return Text(f"{lbl} {bar_str}", style=style, justify="right")
        else:
            return Text(f"{bar_str} {lbl}", style=style, justify="left")

if __name__ == "__main__":
    app = NexusOIOrderBook()
    app.run()
