import zmq
import nexus_lock
nexus_lock.enforce_singleton()
import json
import requests
import time
import sys
import argparse
import os
import glob
import pandas as pd
import re
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table

# Helper for Parsing Positions
def parse_position_details(p):
    """Parses raw position dict to extract (Symbol, Exp, Type, Strike)."""
    s = p.get('Symbol', '???'); exp = "-"; typ = "?"
    strike = 0.0
    
    # 1. Parse Expiry (Try Field First, then Regex)
    if p.get('ExpirationDate'):
        try:
            d = datetime.fromisoformat(p['ExpirationDate'].replace('Z', '+00:00'))
            exp = d.strftime('%Y-%m-%d')
        except: pass
        
    # 2. Parse Type & Strike & Date from Symbol (OCC Format)
    # Regex: Root + (Date YYMMDD) + (Type C/P) + (Strike 8 digits)
    # Example: SPY 260116P00710000 (Spaces might vary)
    try:
        # Clean symbol
        clean_s = s.replace(" ", "")
        # Look for the OCC pattern: 6 digits (Date), 1 char (C/P), 8 digits (Strike) at end
        m = re.search(r'(\d{6})([CP])(\d{8})$', clean_s)
        
        if m:
            # Parse Date from Symbol if missing
            if exp == "-":
                y, m_date, d_date = m.group(1)[:2], m.group(1)[2:4], m.group(1)[4:]
                exp = f"20{y}-{m_date}-{d_date}"
            
            # Parse Type
            typ = "CALL" if m.group(2) == 'C' else "PUT"
            
            # Parse Strike
            k = float(m.group(3)) / 1000.0
            strike = k
            
            # Root is everything before the date
            root = clean_s.split(m.group(1))[0]
            return root, exp, typ, strike

        # Fallback for non-standard or simple parsing
        m2 = re.search(r'([CP])0*(\d+(?:\.\d+)?)$', s)
        if m2 and "OPTION" in str(p.get('AssetType','')).upper():
            k = float(m2.group(2))
            if k > 10000 and "." not in m2.group(2): k = k/1000 
            strike = k
            typ = "CALL" if m2.group(1) == 'C' else "PUT"
            return s.split()[0], exp, typ, strike
            
        return s.split()[0], "SHARES", "STOCK", 0.0
    except: return s[:8], exp, "?", 0.0

# ... (Imports and Setup) ...

    def execute_emergency_exit(self, reason, targets=None):
        """Liquidates positions matching the targets criteria."""
        console.print(f"[bold red]🚨 INITIATING EMERGENCY EXIT: {reason}[/]")
        
        if DRY_RUN:
            console.print(f"[bold yellow][DRY RUN] WOULD HAVE EXECUTED LIQUIDATION (Targets: {targets})[/]")
            send_discord_alert("DRY RUN EXECUTION", f"Would have liquidated positions matching {targets} due to: {reason}", 0xFFFF00)
            return

        if not self.ts_manager:
            console.print("[bold red][!] Cannot execute: TradeStation not connected.[/]")
            return

        try:
            # 1. Get Positions
            positions = self.ts_manager.get_positions()
            if not positions:
                console.print("[green]No open positions to liquidate.[/]")
                return

            # 2. Filter & Close
            executed_count = 0
            for p in positions:
                sym_raw = p.get('Symbol')
                qty = p.get('Quantity')
                if not sym_raw or not qty: continue
                
                # Parse Details
                root, exp, typ, strike = parse_position_details(p)
                
                # ZOMBIE CHECK (Expired Positions)
                try:
                    if exp != "-":
                        exp_date = datetime.strptime(exp, '%Y-%m-%d').date()
                        if exp_date < datetime.date.today():
                            console.print(f"[yellow]⚠️ SKIPPING ZOMBIE POSITION: {sym_raw} (Expired {exp})[/]")
                            continue
                except: pass
                
                match = True
                fail_reason = ""
                
                # Apply Filters (If targets exist)
                if targets:
                    # Filter by Root Symbol
                    if 'symbol' in targets and targets['symbol'] != root:
                        match = False; fail_reason = f"Root {root} != {targets['symbol']}"
                    
                    # Filter by Type
                    elif 'type' in targets and targets['type'].upper() not in typ:
                        match = False; fail_reason = f"Type {typ} != {targets['type']}"
                    
                    # Filter by Strike
                    elif 'strike' in targets:
                        target_strike = float(targets['strike'])
                        if abs(strike - target_strike) > 0.01:
                            match = False; fail_reason = f"Strike {strike} != {target_strike}"
                            
                    # Filter by Expiry
                    elif 'expiry' in targets:
                        if exp != targets['expiry']:
                            match = False; fail_reason = f"Expiry {exp} != {targets['expiry']}"

                console.print(f"[dim][GUARDIAN] Scanned {sym_raw} ({root} {exp} {strike} {typ}). Match: {match} {f'({fail_reason})' if not match else ''}[/]")

                if match:
                    # Determine Side based on Position Type (Long vs Short)
                    # TS API usually provides 'LongShort': 'Long' or 'Short'
                    pos_type = p.get('LongShort', 'Long').title() # Default to Long (Sell to close)
                    close_side = "Buy" if pos_type == "Short" else "Sell"
                    
                    console.print(f"[bold red]CLOSING {pos_type.upper()} {sym_raw} ({qty}) -> {close_side.upper()}...[/]")
                    resp = self.ts_manager.place_order(sym_raw, qty, side=close_side, order_type="Market")
                    console.print(f"[dim]Order Resp: {resp}[/]")
                    executed_count += 1
                
            if executed_count > 0:
                send_discord_alert("🚨 EXECUTED EMERGENCY EXIT", f"Liquidated {executed_count} positions matching {targets} due to: {reason}", 0xFF0000)
            else:
                console.print("[yellow]No positions matched the exit criteria.[/]")
            
        except Exception as e:
            console.print(f"[bold red][!] Execution Failed: {e}[/]")
            send_discord_alert("EXECUTION FAILED", f"Failed to liquidate: {e}", 0xFF0000)

# Import TradeStation Manager
try:
    from tradestation_explorer import TradeStationManager
except ImportError:
    print("CRITICAL: tradestation_explorer.py not found. Ensure it is in the same directory.")
    sys.exit(1)

DEBUG_MODE = False
# --- CRITICAL SAFETY CONFIG ---
LIVE_TRADING = True         # <--- Master Switch
DRY_RUN = False             # <--- Execution Enabled
ALLOW_IMMEDIATE_TRIGGER = False
console = Console()

# CONFIGURATION
# -----------------------------------------------------------------------------
try:
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID, DISCORD_WEBHOOK_URL, LIVE_TRADING
    YOUR_ACCOUNT_ID = TS_ACCOUNT_ID
except ImportError:
    console.print("[bold red]CRITICAL: nexus_config.py not found![/]")
    sys.exit(1)

# --- ALERT REGISTRY (CONTROL PANEL) ---
ACTIVE_ALERTS = [
    # {
    #     "id": "STRUCTURAL_FAIL_707",
    #     "type": "PRICE", # Live Price
    #     "trigger_value": 707.00,
    #     "condition": ">",
    #     "message": "🚨 STRUCTURAL FAILURE: $700 Wall Broken. Short Squeeze Imminent.",
    #     "color": "DARK_RED"
    # }
]

COLOR_MAP = {
    "RED": 0xFF0000,
    "GREEN": 0x00FF00,
    "YELLOW": 0xFFFF00,
    "BLUE": 0x3498DB,
    "DARK_RED": 0x8B0000
}
# -----------------------------------------------------------------------------

ZMQ_PORT = 9999
ZMQ_PORT_LOGS = 5572 # Nexus Logs
from nexus_config import ZMQ_PORT_NOTIFICATIONS

# --- ZMQ SETUP ---
ctx_alert = zmq.Context()
sock_alert = ctx_alert.socket(zmq.PUSH)
sock_alert.connect(f"tcp://localhost:{ZMQ_PORT_NOTIFICATIONS}")

def send_discord_alert(title, description, color):
    """Sends an embed via ZMQ to the Notification Service."""
    try:
        # Map integer colors back to strings if possible, or pass int directly
        # The receiver handles both.
        payload = {
            "title": title,
            "message": description,
            "color": color # Int or String
        }
        sock_alert.send_json(payload, flags=zmq.NOBLOCK)
        console.print(f"[bold green][➔] Pushed Alert to Service:[/bold green] {title}")
    except Exception as e:
        console.print(f"[bold red][!] Failed to push Alert:[/bold red] {e}")

def print_active_alerts():
    """Prints the startup audit table."""
    table = Table(title="[bold blue]ACTIVE RISK RULES (GUARDIAN)[/]")
    table.add_column("ID", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Trigger", style="yellow")
    table.add_column("Message", style="white")
    
    for alert in ACTIVE_ALERTS:
        trigger_str = f"{alert['condition']} {alert['trigger_value']:.2f}"
        table.add_row(alert['id'], alert['type'], trigger_str, alert['message'])
    
    console.print(table)

class TradeGuardian:
    def __init__(self):
        self.spy_price = 0.0
        self.last_check_time = 0
        self.last_alert_times = {}
        self.check_interval = 300  # 5 minutes
        self.alert_cooldown = 3600 # 60 minutes
        
        self.last_heartbeat_time = 0
        self.heartbeat_interval = 60 # 1 minute

        self.snapshot_data = "No Snapshot Loaded"
        
        # Simulation Mode
        self.sim_4h_close = None
        
        # TradeStation Integration
        self.ts_manager = None
        self.execution_cooldowns = {} # Cache to prevent spam
        self.init_tradestation()

    def init_tradestation(self):
        try:
            self.ts_manager = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, YOUR_ACCOUNT_ID)
            console.print("[green][*] TradeStation Manager Initialized[/]")
        except Exception as e:
            console.print(f"[red][!] Failed to init TradeStation: {e}[/]")

    def update_price(self, price):
        if price > 0:
            self.spy_price = price

    def get_valid_price(self):
        """Returns (price, source_label). Falls back to TS Snapshot if ZMQ is silent."""
        # 1. Try ZMQ Live Price
        if self.spy_price > 0:
            return self.spy_price, "Live"
        
        # 2. Try TradeStation Snapshot
        if self.ts_manager:
            try:
                quote = self.ts_manager.get_quote_snapshot("SPY")
                if quote and "Last" in quote:
                    price = float(quote["Last"])
                    return price, "Fallback"
            except Exception: pass
            
        return 0.0, "N/A"

    def read_latest_snapshot(self):
        try:
            # Look in snapshots/ folder
            list_of_files = glob.glob('snapshots/*.csv') 
            if not list_of_files:
                return
            latest_file = max(list_of_files, key=os.path.getctime)
            self.snapshot_data = f"Loaded: {os.path.basename(latest_file)}"
            if DEBUG_MODE: console.print(f"[dim]Guardian loaded snapshot: {latest_file}[/]")
        except Exception as e:
            if DEBUG_MODE: console.print(f"[dim]Snapshot load err: {e}[/]")

    def get_4h_close(self):
        """Fetches the last CLOSED 4-hour candle close price."""
        # Simulation Override
        if self.sim_4h_close is not None:
            console.print(f"[bold yellow][TEST] Using Simulated 4H Close: ${self.sim_4h_close:.2f}[/]")
            return self.sim_4h_close

        if not self.ts_manager: return None
        try:
            # Interval 240 = 4 Hours
            bars = self.ts_manager.get_historical_data("SPY", interval="240", unit="Minute", bars_back="2")
            if bars and len(bars) >= 2:
                # The last bar (index -1) is usually the current forming bar.
                # The second to last (index -2) is the last CLOSED bar.
                last_closed = bars[-2]
                close_price = float(last_closed.get('Close', 0))
                ts = last_closed.get('TimeStamp', 'Unknown')
                if DEBUG_MODE: console.print(f"[dim]Fetched 4H Candle: {ts} Close=${close_price:.2f}[/]")
                return close_price
        except Exception as e:
            console.print(f"[red][!] TS API Error: {e}[/]")
        return None

    def check(self, force=False):
        now = time.time()
        if not force and (now - self.last_check_time < self.check_interval):
            return

    def check(self, force=False):
        now = time.time()
        if not force and (now - self.last_check_time < self.check_interval):
            return

        self.last_check_time = now
        self.read_latest_snapshot()
        
        # Get Price
        price, source = self.get_valid_price()
        if price == 0:
            if DEBUG_MODE: console.print("[dim]No valid price for check.[/]")
            return

        # Check Alerts
        for alert in ACTIVE_ALERTS:
            # Check Cooldown
            last_triggered = alert.get('last_triggered', 0)
            if now - last_triggered < self.alert_cooldown:
                continue
            
            # Safety: Don't trigger if already closed
            if getattr(self, 'position_closed', False) and alert.get('action') == 'EXECUTE':
                continue

            triggered = False
            reason = ""
            val = alert['trigger_value']
            cond = alert['condition']
            alert_type = alert.get('type', 'PRICE')
            
            # --- RULE LOGIC ---
            
            # 1. CANDLE_CLOSE_4H (Thesis Stop)
            if alert_type == 'CANDLE_CLOSE_4H':
                last_4h = self.get_4h_close()
                if last_4h:
                    if cond == '>' and last_4h > val:
                        triggered = True
                        reason = f"Confirmed 4H Close ${last_4h:.2f} > ${val}"
                    elif cond == '<' and last_4h < val:
                        triggered = True
                        reason = f"Confirmed 4H Close ${last_4h:.2f} < ${val}"

            # 2. PRICE (Live Tick / Panic Stop)
            elif alert_type == 'PRICE':
                if cond == '>' and price > val: 
                    triggered = True
                    reason = f"Live Price ${price:.2f} > ${val}"
                elif cond == '<' and price < val: 
                    triggered = True
                    reason = f"Live Price ${price:.2f} < ${val}"
            
            # 3. HYBRID_STOP (Legacy/Fallback)
            elif alert_type == 'HYBRID_STOP':
                last_4h = self.get_4h_close()
                if last_4h and last_4h > val:
                    triggered = True; reason = f"Confirmed 4H Close ${last_4h:.2f} > ${val}"
                elif price > val:
                    dt = datetime.now()
                    if dt.minute == 59 and dt.hour in [9, 13, 17]:
                         triggered = True; reason = f"Near Close Price ${price:.2f} > ${val}"

            # --- EXECUTION ---
            if triggered:
                alert['last_triggered'] = now
                msg = alert['message']
                full_msg = f"{msg} ({reason})"
                
                console.print(Panel(f"[bold {alert['color']}]{full_msg}[/]", title="ALERT TRIGGERED"))
                send_discord_alert(alert['id'], full_msg, 0xFF0000 if alert['color']=='RED' else 0xFFA500)
                
                if alert.get('action') == 'EXECUTE':
                    self.execute_emergency_exit(full_msg, targets=alert.get('targets'))
                    self.position_closed = True # Set Flag to prevent double-fire

    def execute_specific_exit(self, symbol, qty, reason):
        """Liquidates a SPECIFIC position."""
        console.print(f"[bold red]🚨 GUARDIAN SYNC TRIGGER: {reason}[/]")
        
        if DRY_RUN:
            console.print(f"[bold yellow][DRY RUN] WOULD HAVE CLOSED {symbol} ({qty})[/]")
            send_discord_alert("DRY RUN SYNC", f"Would have closed {symbol} ({qty}) due to: {reason}", 0xFFFF00)
            send_discord_alert("DRY RUN SYNC", f"Would have closed {symbol} ({qty}) due to: {reason}", 0xFFFF00)
            return

        # Cooldown Check (Prevent Spam)
        now = time.time()
        last_exec = self.execution_cooldowns.get(symbol, 0)
        if now - last_exec < 60: # 1 Minute Cooldown per symbol
            if DEBUG_MODE: console.print(f"[dim]Skipping execution for {symbol} (Cooldown)[/]")
            return
        self.execution_cooldowns[symbol] = now

        if not self.ts_manager: return

        try:
            # We need to know if we are Long or Short to close correctly.
            # Since this method is triggered by logic that might not have the full position dict,
            # we should fetch the position first to be safe, OR pass the side in.
            # However, 'execute_specific_exit' is called from 'sync_orders' which iterates positions.
            # Let's verify we are passing the correct side logic or fetching it.
            # In sync_orders, we iterate positions 'for p in positions'.
            # We should pass the position object or the side to this function.
            # For now, let's fetch the position again to be absolutely sure we don't 'Sell' a 'Short'.
            
            # OPTIMIZATION: Check if we can pass the side/type from sync_orders
            # But to be robust:
            current_positions = self.ts_manager.get_positions()
            target_pos = next((x for x in current_positions if x.get('Symbol') == symbol), None)
            
            if not target_pos:
                console.print(f"[red]Cannot close {symbol}: Position not found.[/]")
                return

            pos_type = target_pos.get('LongShort', 'Long').title()
            close_side = "Buy" if pos_type == "Short" else "Sell"
            
            console.print(f"[bold red]CLOSING {pos_type.upper()} {symbol} ({qty}) -> {close_side.upper()}...[/]")
            resp = self.ts_manager.place_order(symbol, qty, side=close_side, order_type="Market")
            console.print(f"[dim]Order Resp: {resp}[/]")
            send_discord_alert("🚨 GUARDIAN EXECUTION", f"Closed {symbol} ({qty}) [{close_side}] due to: {reason}", 0xFF0000)
        except Exception as e:
            console.print(f"[bold red][!] Sync Exec Failed: {e}[/]")

    def sync_orders(self):
        """Reads active_targets.json and enforces stops/targets."""
        # Run every 5 seconds (Faster polling as requested)
        now = time.time()
        if now - getattr(self, 'last_sync_time', 0) < 5: return
        self.last_sync_time = now

        # 1. Read Active Targets
        orders = {}
        try:
            # Check active_targets.json FIRST (New System)
            if os.path.exists("active_targets.json"):
                with open("active_targets.json", "r") as f:
                    orders = json.load(f)
            # Fallback to nexus_orders.json if needed, or merge?
            # User specifically asked to watch active_targets.json
        except Exception: return

        self.active_orders_cache = getattr(self, 'active_orders_cache', {})
        
        # Detect Changes and Log
        if orders != self.active_orders_cache:
            diff_added = [k for k in orders if k not in self.active_orders_cache]
            diff_removed = [k for k in self.active_orders_cache if k not in orders]
            
            if diff_added:
                console.print(f"[bold green][GUARDIAN] New Targets Received: {diff_added}[/]")
                for k in diff_added:
                    d = orders[k]
                    pt_str = f"P/T {d.get('take')}"
                    if 'targets' in d and d['targets']:
                        t_list = [f"T{t.get('id', i+1)}:${t.get('price')}" for i, t in enumerate(d['targets'])]
                        pt_str = " | ".join(t_list)
                    
                    console.print(f"   └─ {k}: S/L {d.get('stop')} | {pt_str}")
            
            if diff_removed:
                console.print(f"[bold yellow][GUARDIAN] Targets Removed: {diff_removed}[/]")

            self.active_orders_cache = orders # Update Cache

        if not orders: return
        
        # Sync Log (As requested)
        if DEBUG_MODE:
            console.print(f"[dim][Guardian] Refreshed active targets. Count: {len(orders)}[/]")

        # 2. Get Open Positions & Valid Price
        if not self.ts_manager: return
        positions = self.ts_manager.get_positions()
        if not positions: return
        
        # We need the LIVE price of the OPTION, not just SPY.
        # This is tricky. alert_manager only gets SPY price from ZMQ.
        # It doesn't get Option prices unless we subscribe to them?
        # Wait, the Dashboard gets Option prices via 'SELECT' or 'OPTION_TICK'.
        # Alert Manager is listening to SUB "" (Everything).
        # So it DOES receive option ticks if they are broadcasted.
        # BUT, we need to store them.
        # For now, we will use SPY price for SPY stops, but for Options, we might be blind 
        # unless we add Option Price tracking to Alert Manager.
        # HOWEVER, the Dashboard logic `if stop>0 and p<=stop` usually refers to the OPTION price.
        # If the user sets a stop on SPY (the stock), it works.
        # If the user sets a stop on an OPTION, we need the option price.
        
        # LIMITATION: Guardian currently only tracks SPY Underlying.
        # If the order is for SPY stock, we can enforce it.
        # If it's for an Option, we need the Option Price.
        # I will implement SPY-based checks first.
        # If the user wants Option-Price based stops, I need to cache option prices from ZMQ.
        
        current_spy, _ = self.get_valid_price()
        if current_spy == 0: return

        for p in positions:
            sym = p.get('Symbol')
            qty = p.get('Quantity')
            if sym not in orders: continue
            
            rule = orders[sym]
            stop = float(rule.get('stop', 0))
            take = float(rule.get('take', 0))
            typ = rule.get('type', 'C') # 'C' or 'P' or 'S' (Stock)
            
            # If Symbol is SPY, we can check directly
            if sym == "SPY":
                triggered = False
                reason = ""
                # Long Stock Logic
                if stop > 0 and current_spy <= stop: triggered=True; reason=f"STOP LOSS {stop}"
                elif take > 0 and current_spy >= take: triggered=True; reason=f"TAKE PROFIT {take}"
                
                if triggered:
                    self.execute_specific_exit(sym, qty, reason)
            
            # If it's an Option, we assume the Stop is based on the OPTION PRICE, 
            # which we might not have. 
            # UNLESS the user sets stops based on UNDERLYING levels?
            # Dashboard code: `if stop>0 and p<=stop`. `p` comes from `sub_mkt` (SPY Price) OR `sub_tik`?
            # In Dashboard `sub_mkt`: `p=_to_float(d.get('Last',0))`. This is SPY price.
            # Wait, `sub_mkt` updates `self.query_one(ExecutionPanel).und_price`.
            # And the fallback check uses `p` (SPY Price) to check stops?
            # Line 274 in trader_dashboard.py: `for sym, r in list(self.oco.items()): ... if stop>0 and p<=stop ...`
            # YES! The Dashboard uses SPY PRICE to trigger Option Stops (Mental Stops on Underlying).
            # So Guardian CAN enforce this!
            
            else:
                # Option Logic (Based on SPY Price)
                triggered = False
                reason = ""
                is_call = typ.upper().startswith('C')
                
                if is_call:
                    if stop > 0 and current_spy <= stop: triggered=True; reason=f"STOP (SPY <= {stop})"
                    elif take > 0 and current_spy >= take: triggered=True; reason=f"TAKE (SPY >= {take})"
                else: # Put
                    if stop > 0 and current_spy >= stop: triggered=True; reason=f"STOP (SPY >= {stop})"
                    elif take > 0 and current_spy <= take: triggered=True; reason=f"TAKE (SPY <= {take})"

                if triggered:
                    self.execute_specific_exit(sym, qty, reason)

    def execute_emergency_exit(self, reason, targets=None):
        """Liquidates positions matching the targets criteria."""
        console.print(f"[bold red]🚨 INITIATING EMERGENCY EXIT: {reason}[/]")
        
        if DRY_RUN:
            console.print(f"[bold yellow][DRY RUN] WOULD HAVE EXECUTED LIQUIDATION (Targets: {targets})[/]")
            send_discord_alert("DRY RUN EXECUTION", f"Would have liquidated positions matching {targets} due to: {reason}", 0xFFFF00)
            return

        if not self.ts_manager:
            console.print("[bold red][!] Cannot execute: TradeStation not connected.[/]")
            return

        try:
            # 1. Get Positions
            positions = self.ts_manager.get_positions()
            if not positions:
                console.print("[green]No open positions to liquidate.[/]")
                return

            # 2. Filter & Close
            executed_count = 0
            for p in positions:
                sym_raw = p.get('Symbol')
                qty = p.get('Quantity')
                if not sym_raw or not qty: continue
                
                # Parse Details
                root, exp, typ, strike = parse_position_details(p)
                
                match = True
                fail_reason = ""
                
                # Apply Filters (If targets exist)
                if targets:
                    # Filter by Root Symbol
                    if 'symbol' in targets and targets['symbol'] != root:
                        match = False; fail_reason = f"Root {root} != {targets['symbol']}"
                    
                    # Filter by Type
                    elif 'type' in targets and targets['type'].upper() not in typ:
                        match = False; fail_reason = f"Type {typ} != {targets['type']}"
                    
                    # Filter by Strike
                    elif 'strike' in targets:
                        target_strike = float(targets['strike'])
                        if abs(strike - target_strike) > 0.01:
                            match = False; fail_reason = f"Strike {strike} != {target_strike}"
                            
                    # Filter by Expiry
                    elif 'expiry' in targets:
                        if exp != targets['expiry']:
                            match = False; fail_reason = f"Expiry {exp} != {targets['expiry']}"

                console.print(f"[dim][GUARDIAN] Scanned {sym_raw} ({root} {exp} {strike} {typ}). Match: {match} {f'({fail_reason})' if not match else ''}[/]")

                if match:
                    console.print(f"[bold red]CLOSING {sym_raw} ({qty})...[/]")
                    resp = self.ts_manager.place_order(sym_raw, qty, side="Sell", order_type="Market")
                    console.print(f"[dim]Order Resp: {resp}[/]")
                    executed_count += 1
                
            if executed_count > 0:
                send_discord_alert("🚨 EXECUTED EMERGENCY EXIT", f"Liquidated {executed_count} positions matching {targets} due to: {reason}", 0xFF0000)
            else:
                console.print("[yellow]No positions matched the exit criteria.[/]")
            
        except Exception as e:
            console.print(f"[bold red][!] Execution Failed: {e}[/]")
            send_discord_alert("EXECUTION FAILED", f"Failed to liquidate: {e}", 0xFF0000)

    def check(self, force=False):
        now = time.time()
        if not force and (now - self.last_check_time < self.check_interval):
            return

        self.last_check_time = now
        self.read_latest_snapshot()
        
        # Optimization: Fetch 4H Close ONCE if needed
        spy_4h_close = None
        needs_candle = any(a['type'] == 'CANDLE_CLOSE' or a['type'] == 'HYBRID_STOP' for a in ACTIVE_ALERTS)
        if needs_candle:
            spy_4h_close = self.get_4h_close()

        # Get Valid Live Price (or Fallback)
        current_price, price_source = self.get_valid_price()
        
        # Check Time for Hybrid Stop (Near 4H Close)
        # Assuming 4H closes at 14:00 and 18:00 ET (User said 13:59, 17:59)
        # We check if current minute is 59 and hour is 13 or 17 (or others if needed)
        dt = datetime.now()
        is_near_close = (dt.minute == 59) and (dt.hour in [13, 17, 9]) # Added 9 for 10am close? User said 13:59, 17:59.

        for alert in ACTIVE_ALERTS:
            triggered = False
            current_val = 0.0
            
            # Determine Value to Check
            if alert['type'] == 'PRICE':
                if current_price == 0: continue
                current_val = current_price
                if alert['condition'] == '>' and current_val > alert['trigger_value']: triggered = True
                elif alert['condition'] == '<' and current_val < alert['trigger_value']: triggered = True
                
            elif alert['type'] == 'CANDLE_CLOSE':
                if spy_4h_close is None: continue
                current_val = spy_4h_close
                if alert['condition'] == '>' and current_val > alert['trigger_value']: triggered = True
                elif alert['condition'] == '<' and current_val < alert['trigger_value']: triggered = True
                
            elif alert['type'] == 'HYBRID_STOP':
                # 1. Check Confirmed 4H Close
                if spy_4h_close and spy_4h_close > alert['trigger_value']:
                    triggered = True
                    current_val = spy_4h_close
                
                # 2. Check "Near Close" Condition (Live Price > Level AND Time is :59)
                elif is_near_close and current_price > alert['trigger_value']:
                    triggered = True
                    current_val = current_price
                    console.print(f"[bold red]⚠️ NEAR 4H CLOSE DETECTED ({dt.strftime('%H:%M')}) - CHECKING LIVE PRICE[/]")

            if triggered:
                color_hex = COLOR_MAP.get(alert.get('color', 'RED'), 0xFF0000)
                source_note = f" (Source: {price_source})" if alert['type'] == 'PRICE' else " (Source: 4H Candle/Live)"
                full_msg = f"{alert['message']}\n(Trigger: {current_val:.2f} {alert['condition']} {alert['trigger_value']:.2f}{source_note})\nContext: {self.snapshot_data}"
                
                self.trigger_alert(
                    alert['id'],
                    f"GUARDIAN ALERT: {alert['id']}",
                    full_msg,
                    color_hex
                )
                
                # EXECUTE IF ACTION IS SET
                if alert.get('action') == 'EXECUTE':
                    self.execute_emergency_exit(full_msg, targets=alert.get('targets'))

    def heartbeat(self):
        now = time.time()
        if now - self.last_heartbeat_time < self.heartbeat_interval:
            return

        self.last_heartbeat_time = now
        
        # Fetch 4H Close
        spy_4h = self.get_4h_close()
        spy_4h_str = f"${spy_4h:.2f}" if spy_4h else "N/A"
        
        # Fetch Valid Price
        price, source = self.get_valid_price()
        
        # Format Targets String
        targets_str = ""
        if hasattr(self, 'active_orders_cache') and self.active_orders_cache:
            t_list = []
            for sym, data in self.active_orders_cache.items():
                sl = data.get('stop', 0)
                if sl > 0: t_list.append(f"{sym} S/L {sl}")
            if t_list:
                targets_str = f" (Target: {', '.join(t_list)})"
        
        # Mode Indicator
        mode_str = "[bold yellow]SIMULATION (DRY RUN)[/]" if DRY_RUN else "[bold red]🚨 LIVE TRADING 🚨[/]"
        
        console.print(f"[dim][HEARTBEAT] SPY: ${price:.2f} ({source}) | Last 4H Close: {spy_4h_str} | Mode: {mode_str} | Guardian: [bold green]ARMED[/]{targets_str}[/]")

    def trigger_alert(self, alert_key, title, desc, color):
        now = time.time()
        last_time = self.last_alert_times.get(alert_key, 0)
        
        if now - last_time > self.alert_cooldown:
            console.print(Panel(f"[bold]{title}[/]\n{desc}", title="GUARDIAN ALERT", border_style="red"))
            send_discord_alert(title, desc, color)
            self.last_alert_times[alert_key] = now

def main():
    # Startup Banner
    console.clear()
    console.print(Panel.fit(
        f"[bold white]NEXUS TRADING SYSTEM[/]\n"
        f"[dim]Guardian Module v2.5[/]\n\n"
        f"Execution Mode: {'[bold yellow]SIMULATION (DRY RUN)[/]' if DRY_RUN else '[bold red]🚨 LIVE TRADING ENABLED 🚨[/]'}\n"
        f"Discord Webhook: {'[green]Connected[/]' if DISCORD_WEBHOOK_URL else '[red]Missing[/]'}\n"
        f"TradeStation: {'[green]Ready[/]' if TS_CLIENT_ID else '[red]Missing Credentials[/]'}",
        title="SYSTEM STARTUP", border_style="blue"
    ))
    
    if not DRY_RUN:
        console.print("[bold red blink]WARNING: REAL MONEY TRADING IS ENABLED. SYSTEM CAN EXECUTE ORDERS.[/]")
        console.print("[bold red][WARNING] GUARDIAN IS LIVE. REAL EXECUTION ENABLED.[/]")
        time.sleep(3)
    
    print_active_alerts()
    
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    
    # Connect to the Publisher (uw_nexus.py)
    try:
        socket.connect(f"tcp://localhost:{ZMQ_PORT}")
        socket.connect("tcp://localhost:9998") # Test Port
        socket.connect(f"tcp://localhost:{ZMQ_PORT_LOGS}") # Nexus Logs
        console.print(f"[green][*] Connected to Ports: {ZMQ_PORT}, 9998, {ZMQ_PORT_LOGS}[/]")
    except zmq.ZMQError as e:
        console.print(f"[bold red][!] Could not connect to ports: {e}[/]")
        sys.exit(1)
        
    # Subscribe to all messages
    socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    guardian = TradeGuardian()
    
    console.print("[dim][*] Waiting for alerts...[/]")
    
    while True:
        try:
            # Non-blocking check for ZMQ messages
            if socket.poll(1000): # Wait up to 1s
                msg = socket.recv_multipart()
                if len(msg) < 2 or not msg[1]: continue 

                try:
                    message = json.loads(msg[1].decode('utf-8'))
                    
                    # Update Guardian Price (Live)
                    ticker = message.get('ticker', '')
                    if "SPY" in ticker:
                        price = float(message.get('underlying_price') or message.get('stock_price') or 0)
                        if price > 0: guardian.update_price(price)
                    
                    # Handle Simulation Data
                    if "sim_4h_close" in message:
                        guardian.sim_4h_close = float(message["sim_4h_close"])
                        console.print("[bold yellow][TEST] Received Simulation Data. Forcing Check...[/]")
                        guardian.check(force=True)
                        
                except Exception: pass
                
                # Process Alerts (Existing Logic)
                except Exception: pass
                
                # Process Alerts (Existing Logic)
                try:
                    # 1. JSON Messages (Whale Alerts)
                    if isinstance(message, dict):
                        msg_type = message.get("type")
                        z_score = message.get("z_score", 0.0)
                        
                        if DEBUG_MODE: console.print(f"[dim][>] Received: {message}[/]")
                        
                        if msg_type == "TEST":
                            console.print(Panel("[bold blue]System Online[/]\nThe Alert Manager is receiving messages.", title="TEST", border_style="blue"))
                            send_discord_alert("System Online", "The Alert Manager is receiving messages.", 0x3498DB)
                            
                        elif msg_type == "ALERT":
                            if z_score > 4.0:
                                console.print(Panel(f"[bold red]🚨 Bearish Whale Alert[/]\nZ-Score: {z_score:.2f}", title="ALERT", border_style="red"))
                                send_discord_alert("🚨 Bearish Whale Alert", f"Z-Score: {z_score:.2f}", 0xFF0000)
                            elif z_score < -4.0:
                                console.print(Panel(f"[bold green]🟢 Bullish Whale Alert[/]\nZ-Score: {z_score:.2f}", title="ALERT", border_style="green"))
                                send_discord_alert("🟢 Bullish Whale Alert", f"Z-Score: {z_score:.2f}", 0x00FF00)
                    
                    # 2. Log Messages (Nexus Execution Events)
                    # The message might be a raw string if it came from LOGS port, but we did json.loads above.
                    # ts_nexus sends [b"LOG", b"Message"]
                    # If we are here, 'message' is the JSON payload of the SECOND frame.
                    # Wait, ts_nexus sends a STRING in the second frame for logs, not JSON.
                    # So json.loads might have failed for raw text logs.
                    pass
                except Exception: pass

                # Handle Raw Text Logs (Nexus)
                # If json.loads failed, we might have raw text in msg[1]
                try:
                    raw_text = msg[1].decode('utf-8')
                    # Nexus Log Format: [HH:MM:SS] Message
                    
                    if "TRIGGER FIRED" in raw_text:
                        # Extract Symbol and Reason
                        # Example: [12:00:00] [bold red]TRIGGER FIRED: SPY (TARGET 680 >= 680) Qty:1[/]
                        clean_text = re.sub(r'\[.*?\]', '', raw_text).strip() # Remove color tags
                        send_discord_alert("🎯 TARGET HIT", clean_text, 0x00FF00)
                        console.print(f"[bold green]>> ALERT SENT: {clean_text}[/]")
                        
                    elif "ARMED:" in raw_text:
                        clean_text = re.sub(r'\[.*?\]', '', raw_text).strip()
                        send_discord_alert("🛡️ POSITION ARMED", clean_text, 0xFFFF00)
                        
                    elif "DISARMED:" in raw_text:
                        clean_text = re.sub(r'\[.*?\]', '', raw_text).strip()
                        send_discord_alert("⚪ POSITION DISARMED", clean_text, 0x95A5A6)
                        
                    elif "EXEC:" in raw_text:
                        clean_text = re.sub(r'\[.*?\]', '', raw_text).strip()
                        send_discord_alert("⚡ ORDER EXECUTED", clean_text, 0x3498DB)
                        
                except: pass

            # Run Guardian Check (Every loop, but internally throttled)
            guardian.check()
            guardian.heartbeat()
            guardian.sync_orders()

        except KeyboardInterrupt:
            console.print("\n[bold yellow][*] Stopping Alert Manager...[/]")
            break
        except Exception as e:
            console.print(f"[bold red][!] Error processing message: {e}[/]")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()
    DEBUG_MODE = args.debug
    main()
