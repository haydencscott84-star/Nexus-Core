import os
import json
import time
import datetime
import glob
import pandas as pd
import sys
import requests
import math
import zmq
import asyncio
from supabase_bridge import upload_json_to_supabase

# --- CONFIG ---
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"
CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
# --- CONFIG ---
SHEET_ID = "1NMJzjidLxQ0MN8TqvBtwmvOXT_Gur-InljS0VKy2Tfg"
CREDENTIALS_FILE = "tribal-flux-476216-c0-70e4f946eb77.json"
MARKET_STATE_FILE = "market_state.json"
SPY_PROFILE_FILE = "nexus_spy_profile.json"
SPX_PROFILE_FILE = "nexus_spx_profile.json"
STRUCTURE_FILE = "nexus_structure.json"
ACTIVE_PORTFOLIO_FILE = "active_portfolio.json"
ZMQ_PORT_MARKET = 5555

# API KEYS
try: from nexus_config import ORATS_API_KEY
except: ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
UW_API_KEY = os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY")

# Trigger Times (ET)
# Trigger Times (ET)
# Main Slots: 10:05, 13:00, 15:45
# Hourly: 09:30, 10:00, 11:00, 12:00, 14:00, 15:00, 16:00
# Accounts Dump: 18:00
TRIGGERS = ["09:30", "10:00", "10:05", "11:00", "12:00", "13:00", "14:00", "15:00", "15:45", "16:00", "16:30", "18:00"]
MAIN_TRIGGERS = ["10:05", "13:00", "15:45"]
LAST_TRIGGER = None

# --- DEPENDENCY CHECK ---
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    print("❌ MISSING DEPENDENCIES: pip install gspread oauth2client pandas requests pyzmq")
    sys.exit(1)

import zoneinfo

def get_et_now():
    tz = zoneinfo.ZoneInfo("America/New_York")
    return datetime.datetime.now(tz).replace(tzinfo=None)

def load_json(fpath):
    try:
        if os.path.exists(fpath):
            with open(fpath, 'r') as f: return json.load(f)
    except: pass
    return {}

def fetch_vix():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, params={'interval':'1d','range':'1d'}, timeout=5)
        data = r.json()
        price = data['chart']['result'][0]['meta']['regularMarketPrice']
        return float(price)
    except: return 0.0

def fetch_iv_rank(ticker="SPY"):
    try:
        url = f"https://api.unusualwhales.com/api/stock/{ticker}/iv-rank"
        headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data: return float(data[-1].get('iv_rank_1y', 0))
    except: pass
    return 0.0

def fetch_orats_iv(ticker="SPY"):
    try:
        url = "https://api.orats.io/datav2/live/summaries"
        params = {'token': ORATS_API_KEY, 'ticker': ticker}
        r = requests.get(url, params=params, timeout=5)
        if r.status_code == 200:
            d = r.json().get('data', [{}])[0]
            return float(d.get('iv30d', 0))
    except: pass
    return 0.0

def fetch_nexus_price(timeout=15.0):
    """
    Connects to ZMQ Port 5555 to get the TRUE Nexus SPY Price.
    """
    print("🔌 Connecting to Nexus ZMQ (127.0.0.1:5555) for Price...")
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{ZMQ_PORT_MARKET}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "SPY")
    
    start = time.time()
    last_price = 0.0
    
    while time.time() - start < timeout:
        try:
            # Non-blocking check
            if socket.poll(100):
                msg = socket.recv_multipart()
                topic = msg[0].decode()
                payload = json.loads(msg[1])
                if topic == "SPY" and "Last" in payload:
                    last_price = float(payload["Last"])
                    if last_price > 0:
                        return last_price 
        except: pass
        
    socket.close()
    context.term()
    return last_price

def fetch_yahoo_price(ticker):
    """Fallback to Yahoo."""
    try:
        if ticker == "SPX": y_ticker = "^GSPC"
        elif ticker == "SPY": y_ticker = "SPY"
        else: y_ticker = ticker
        
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{y_ticker}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, params={'interval':'1m','range':'1d'}, timeout=5)
        data = r.json()
        price = data['chart']['result'][0]['meta']['regularMarketPrice']
        return float(price)
    except: return 0.0

def get_sheet_service():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).sheet1 
    return sheet

def get_workbook():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(SHEET_ID)


def log_debug(msg):
    try:
        ts = get_et_now().strftime("%H:%M:%S")
        with open("logs/bridge_debug.log", "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except: pass

def run_account_dump():
    print("🚀 TRIGGERING ACCOUNT DUMP (18:00)")
    acct = load_json(ACTIVE_PORTFOLIO_FILE)
    if not acct:
        print(f"⚠️ No Account Data Found in {ACTIVE_PORTFOLIO_FILE}")
        return

    now_str = get_et_now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Extract (Defensive)
    balance = float(acct.get("total_account_value", 0))
    todays_pnl = float(acct.get("todays_pnl", 0))
    ytd_pnl = float(acct.get("ytd_pnl", 0))
    cap_exp = float(acct.get("value_of_open_positions", 0))
    unrealized_pnl = float(acct.get("unrealized_pnl", 0))

    # --- FORMATTING LOGIC ---
    def fmt_pct_val(val, baseline):
        if baseline == 0: return f"0.00% (${val:,.2f})"
        pct = (val / baseline) * 100
        return f"{pct:+.2f}% (${val:+.2f})"

    # Calculate Baselines
    start_day = balance - todays_pnl
    todays_str = fmt_pct_val(todays_pnl, start_day)
    
    start_year = balance - ytd_pnl
    ytd_str = fmt_pct_val(ytd_pnl, start_year)

    # Exposure is always % of Current Balance
    # Exposure is typically absolute value? Or market value?
    # 'value_of_open_positions' can be negative for shorts.
    # Usually exposure % is abs(exp) / balance. But let's keep sign for now if user wants value.
    # Requested: "% bracketed $ value".
    exp_str = fmt_pct_val(cap_exp, balance)
    
    # Notes: Current PNL (Unrealized)
    unrealized_str = fmt_pct_val(unrealized_pnl, balance)
    notes = unrealized_str

    row = [
        now_str,
        f"${balance:,.2f}",
        todays_str, 
        ytd_str,
        exp_str,    # Col E: Capital Exposure Formatted
        notes       # Col F: Unrealized PNL Formatted
    ]
    
    try:
        wb = get_workbook()
        # [ROBUST] Specific Tab Access
        try:
             ws = wb.worksheet("Accounts")
        except:
             print("⚠️ 'Accounts' tab not found. Creating it...")
             ws = wb.add_worksheet(title="Accounts", rows=1000, cols=10)
             ws.append_row(["Date/ Time", "Account Balance", "Todays PNL", "Year To Date PNL", "capital exposure", "Account Notes"])

        ws.append_row(row)
        print(f"✅ ACCOUNT DUMP COMPLETE: {row}")
    except Exception as e:
        print(f"❌ ACCOUNT DUMP FAIL: {e}")


def run_orats_oi_dump():
    print("🚀 TRIGGERING ORATS EOD OI DUMP (16:30)")
    
    trade_date = get_et_now().strftime("%Y-%m-%d")
    url = "https://api.orats.io/datav2/strikes"
    
    rows_to_insert = []
    
    for ticker in ['SPX', 'SPXW', 'SPY']:
        params = {
            'token': ORATS_API_KEY,
            'ticker': ticker,
            'tradeDate': trade_date
        }
        
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json().get('data', [])
        except Exception as e:
            print(f"❌ ORATS API FAILED ({ticker}): {e}")
            continue
            
        if not data:
            print(f"⚠️ ORATS Payload Empty for {ticker}.")
            continue
            
        # [NEW] Extract the official ORATS EOD Spot Price from the first valid contract
        try:
            stock_price = data[0].get('stockPrice', 0.0)
            if stock_price > 0:
                with open("orats_spot_price.txt", "w") as f:
                    f.write(str(stock_price))
                print(f"💰 Saved Official ORATS EOD Price ({ticker}): ${stock_price}")
        except Exception as e:
            print(f"⚠️ Could not save ORATS Spot Price: {e}")
            
        for item in data:
            exp_date_str = item.get('expirDate')
            if not exp_date_str: continue
            
            try:
                exp_date = datetime.datetime.strptime(exp_date_str, "%Y-%m-%d").date()
                if exp_date.weekday() != 4: continue # Friday Expire Only
                
                strike = float(item.get('strike', 0.0))
                c_vol = int(item.get('callVolume', 0))
                c_oi = int(item.get('callOpenInterest', 0))
                rows_to_insert.append([trade_date, exp_date_str, strike, 'Call', c_vol, c_oi])
                
                p_vol = int(item.get('putVolume', 0))
                p_oi = int(item.get('putOpenInterest', 0))
                rows_to_insert.append([trade_date, exp_date_str, strike, 'Put', p_vol, p_oi])
                
            except Exception as e:
                continue
            
    if not rows_to_insert:
        print("⚠️ No Friday expiries found in ORATS payload.")
        return
            
    try:
        wb = get_workbook()
        try:
            ws = wb.worksheet("Historical Data")
        except:
            ws = wb.add_worksheet(title="Historical Data", rows=1000, cols=10)
            ws.append_row(["Trade Date", "Expiration", "Strike", "Type", "Volume", "Open Interest"])
            
        # Bulk Upload
        ws.append_rows(rows_to_insert)
        print(f"✅ ORATS EOD DUMP COMPLETE: {len(rows_to_insert)} records injected into 'Historical Data'.")
    except Exception as e:
        print(f"❌ ORATS EOD DUMP FAIL: {e}")


def run_update(session_label):
    print(f"🚀 TRIGGERING UPDATE: {session_label}")
    
    state = load_json(MARKET_STATE_FILE)
    profile = load_json(SPY_PROFILE_FILE)
    structure = load_json(STRUCTURE_FILE)
    spx_profile = load_json(SPX_PROFILE_FILE)
    
    now_str = get_et_now().strftime("%Y-%m-%d")
    
    # 1. FETCH SPY PRICE (Nexus ZMQ Only)
    spy_price = fetch_nexus_price(timeout=15)
    if spy_price == 0:
        print("⚠️ ZMQ Silent. Using SNAPSHOT fallback (No Yahoo).")
        spy_struct = state.get("market_structure", {}).get("SPY", {})
        spy_price = spy_struct.get("price", 0)
    
    # 2. FETCH SPX PRICE & BASIS
    spx_struct = state.get("market_structure", {}).get("SPX", {})
    spx_price = spx_struct.get("price", 0)
    
    # Calculate Basis (Unified)
    basis = float(state.get("market_structure", {}).get("basis", 0))
    if basis == 0 and spx_price > 0 and spy_price > 0:
        basis = spx_price - (spy_price * 10)
        
    def to_spy(val):
        try:
            v = float(val)
            if basis != 0: return (v - basis) / 10
        except: pass
        return 0.0

    # Format SPX Price
    spx_str = str(spx_price)
    if spx_price > 0:
        s_eq = to_spy(spx_price)
        spx_str = f"{spx_price} (${s_eq:.2f})"

    # GEX Data
    spy_struct = state.get("market_structure", {}).get("SPY", {}) 
    spy_net_gex = str(spy_struct.get("net_gex", "N/A")).replace("(Bearish)", "(Slippery)").replace("(Bullish)", "(Sticky)")
    spx_net_gex = str(spx_struct.get("net_gex", "N/A")).replace("(Bearish)", "(Slippery)").replace("(Bullish)", "(Sticky)")
    
    # Magnet Logic
    # [ROBUST] Fallback to Profile if State is empty
    mag_val = spx_struct.get("levels", {}).get("magnet", "N/A")
    if mag_val == "N/A" or float(mag_val) < 100:
         # Try Profile
         mag_val = profile.get("major_levels", {}).get("magnet", "N/A")

    magnet_str = "N/A"
    try:
        # [FIX] Sanity Check: SPX must be > 100 to be valid. 0 implies data failure.
        if mag_val != "N/A" and float(mag_val) > 100:
            m_eq = to_spy(mag_val)
            magnet_str = f"{mag_val} (${m_eq:.2f})"
            print(f"🧲 MAGNET FOUND: {magnet_str}")
        else:
            print(f"⚠️ MAGNET MISSING (Val: {mag_val})")
    except: magnet_str = str(mag_val)

    # ZERO GAMMA (FLIP) Logic
    zg_str = "N/A"
    try:
        # [FIX] Read from BRIDGE mapped key 'zero_gamma' which now contains 'gamma_flip_strike'
        spy_flip = float(spy_struct.get("zero_gamma", 0))
        if spy_flip > 0:
            zg_str = f"${spy_flip:.2f}"
    except Exception as e: pass

    # Regime (Extracted from quant_analysis)
    quant = state.get("quant_analysis", {})
    spx_regime = quant.get("SPX", {}).get("regime", "N/A")
    spy_regime = quant.get("SPY", {}).get("regime", "N/A")
    
    # Use SPX Regime as the primary context for the dashboard, fallback to SPY, fallback to generic
    mr = spx_regime
    if mr == "N/A" and spy_regime != "N/A": mr = spy_regime
    if mr == "N/A": mr = state.get("flow_sentiment", {}).get("tape", {}).get("momentum_label", "N/A")
    
    call_wall = spy_struct.get("call_wall", 0)
    put_wall = spy_struct.get("put_wall", 0)
    no_fly = "CLEAR"
    if "CHOP" in mr or "INSTABILITY" in mr: no_fly = f"ACTIVE ({mr})"
    elif put_wall > 0 and call_wall > 0:
        rnge = call_wall - put_wall
        if rnge < 5.0: no_fly = f"ACTIVE (Tight ${rnge})"

    # [ROBUST] SMA Calculation with Type Safety
    structure_spy = structure.get("SPY", {})
    sma20 = structure_spy.get("levels", {}).get("sma_20", 0.0)
    sma50 = structure_spy.get("levels", {}).get("sma_50", 0.0)
    sma_dev_str = "N/A"
    sma50_str = "N/A"
    
    try:
        if isinstance(spy_price, (int, float)) and spy_price > 0:
            if isinstance(sma20, (int, float)) and sma20 > 0:
                diff_pct = ((spy_price - sma20) / sma20) * 100
                # [FIX] Prepend ' to force string interpretation in Sheets
                sma_dev_str = f"{diff_pct:+.2f}% (${sma20:.2f})"
                
            if isinstance(sma50, (int, float)) and sma50 > 0:
                diff50_pct = ((spy_price - sma50) / sma50) * 100
                # [FIX] Prepend ' to prevent #ERROR! (Formula Parse)
                sma50_str = f"{diff50_pct:+.2f}% (${sma50:.2f})"
    except Exception as e:
        print(f"⚠️ SMA Calc Error: {e}")
        sma_dev_str = "ERR"
        sma50_str = "ERR"

    # NEW METRICS
    ivr = fetch_iv_rank("SPY")
    ivr_str = f"{ivr:.0f}%"
    vix = fetch_vix()
    vix_str = f"{vix:.2f}"
    
    # VIX Curve (VIX9D/VIX)
    vix9d = fetch_yahoo_price("^VIX9D")
    curve_str = "N/A"
    if vix > 0 and vix9d > 0:
        curve_str = f"{(vix9d / vix):.2f}"
    
    # RVOL (From nexus_structure.json)
    # [FIX] Switch to HOURLY RVOL per User Request
    rvol_val = structure_spy.get("trend_metrics", {}).get("hourly_rvol", 0)
    rvol_str = f"{rvol_val:.2f}"
    
    # Walls (SPX Major Levels -> Converted to SPY)
    cw_str, pw_str = "N/A", "N/A"
    try:
        # Define base walls first to avoid reference error
        spx_call_strike = 0
        spx_put_strike = 0
        
        # Load Wall Context (Delta Premium)
        walls_ctx = {}
        if os.path.exists("nexus_walls_context.json"):
            with open("nexus_walls_context.json", 'r') as f: walls_ctx = json.load(f)

        mix = spx_profile.get("major_levels", {})
        spx_call_strike = float(mix.get("call", 0))
        spx_put_strike = float(mix.get("put", 0))
        
        # Helper for Formatting Power
        def fmt_num_short(val):
            if not val: return ""
            v = abs(float(val))
            s = ""
            if v >= 1e9: s = f"${v/1e9:.1f}B"
            elif v >= 1e6: s = f"${v/1e6:.1f}M"
            else: s = f"${v/1e3:.0f}K"
            return ("+" if float(val) > 0 else "-") + s

        def fmt_wall_str(strike, type_key):
             if strike <= 0: return "N/A"
             
             # 1. Base Conversion
             spy_eq_price = to_spy(strike)
             
             # 2. GEX Power (From Profile)
             gex_power = 0
             gex_list = spx_profile.get("gex_structure", [])
             if gex_list:
                 for stats in gex_list:
                     for key in ['short_gamma_wall_above', 'long_gamma_wall_above', 'short_gamma_wall_below', 'long_gamma_wall_below']:
                         obj = stats.get(key)
                         # [FIX] Handle Float vs Dict
                         stk = 0
                         gex_val = 0
                         if isinstance(obj, dict):
                             stk = float(obj.get('strike', 0))
                             gex_val = float(obj.get('total_gamma_exp', 0))
                         elif isinstance(obj, (int, float)):
                             stk = float(obj)
                             # No GEX Power available in simple float structure
                             gex_val = 0
                         
                         if stk > 0 and abs(stk - strike) < 0.1:
                             if gex_val != 0: gex_power = gex_val
                             break
            
             # Power String
             pwr_str = ""
             if gex_power != 0:
                 v = abs(gex_power)
                 if v >= 1e9: pwr_str = f" (${v/1e9:.1f}B)"
                 elif v >= 1e6: pwr_str = f" (${v/1e6:.0f}M)"
             
             # 3. Context (Delta Premium) from Snapshot
             ctx_str = ""
             spx_walls = walls_ctx.get("SPX", {})
             
             keys_to_try = [str(strike), str(int(strike)) if strike.is_integer() else str(strike), f"{strike:.1f}"]
             
             spx_ctx = None
             match_key = None
             for k in keys_to_try:
                 if k in spx_walls: 
                     spx_ctx = spx_walls[k]
                     match_key = k
                     break
             
             # [PATCH] FUZZY MATCH FALLBACK
             if not spx_ctx:
                 try:
                     for k, v in spx_walls.items():
                         if abs(float(k) - strike) < 0.1:
                             spx_ctx = v
                             match_key = f"FUZZY({k})"
                             break
                 except: pass

             if spx_ctx:
                 d_val = spx_ctx.get('delta', 0)
                 ctx_str = f" [{fmt_num_short(d_val)} Δ]"
                 log_debug(f"💰 PREMIUM FOUND: {strike} (Key: {match_key}) -> {ctx_str}")
             else:
                 log_debug(f"⚠️ NO PREMIUM: {strike} (Tried: {keys_to_try})")
             
             spy_bracket = f" [SPY ${spy_eq_price:.2f}]"
             return f"${strike:.0f}{pwr_str}{spy_bracket}{ctx_str}"

        cw_str = fmt_wall_str(spx_call_strike, "call")
        pw_str = fmt_wall_str(spx_put_strike, "put")
            
    except Exception as e:
        log_debug(f"SPX WALL ERROR: {e}")
        print(f"SPX WALL ERROR: {e}")
        if cw_str == "N/A" and call_wall > 0: cw_str = f"${call_wall:.0f}" 
        if pw_str == "N/A" and put_wall > 0: pw_str = f"${put_wall:.0f}"
    
    # Expected Move (7-Day)
    em_str = "N/A"
    try:
        iv30 = fetch_orats_iv("SPY")
        if spy_price > 0 and iv30 > 0:
            seven_day_sigma = iv30 * math.sqrt(7/365)
            em_val = spy_price * seven_day_sigma
            # Bracket Logic (Low - High)
            upper = spy_price + em_val
            lower = spy_price - em_val
            # [FIX] Removing leading ' as it is visible in the cell
            em_str = f"{lower:.2f} - {upper:.2f} (7D)"
    except: em_str = "N/A"
        
    # SPX RVOL
    structure_spx = structure.get("SPX", {})
    # [FIX] Switch to HOURLY RVOL
    spx_rvol_val = structure_spx.get("trend_metrics", {}).get("hourly_rvol", 0)
    spx_rvol_str = f"{spx_rvol_val:.2f}"

    # FORCE INDEX & TREND STRENGTH
    # Extracted from SPY structure logic 
    fi_val = structure_spy.get("trend_metrics", {}).get("force_index_13", 0)
    fi2_val = structure_spy.get("trend_metrics", {}).get("force_index_2", 0) # NEW
    ts_val = structure_spy.get("trend_metrics", {}).get("trend_strength", 50)
    
    fi_str = f"{fi_val:+.2f}"
    fi2_str = f"{fi2_val:+.2f}" # NEW
    ts_str = f"{ts_val:.0f}"

    # VRP Data (Source of Truth: nexus_vrp_context.json)
    vrp_str = "N/A"
    try:
        if os.path.exists("nexus_vrp_context.json"):
            with open("nexus_vrp_context.json", 'r') as f:
                vrp_data = json.load(f)
                # "vrp_spread": 0.02
                spread = vrp_data.get('vrp_spread', 0)
                # Format: "+2.1% (Sell)"
                sig = "SELL" if spread > 0 else "BUY"
                vrp_str = f"{spread*100:+.2f}% ({sig})"
    except: pass

    # Build Row
    row = [
        now_str,
        session_label,
        str(spx_net_gex),
        str(spy_net_gex),
        spy_price,          
        sma_dev_str,
        sma50_str,
        mr,
        spx_str,            # Updated SPX Price String
        magnet_str,         # Updated Magnet String    
        no_fly,
        ivr_str,
        em_str,
        zg_str,
        vix_str,
        curve_str,
        cw_str,
        pw_str,
        rvol_str,
        spx_rvol_str,       # [NEW] SPX RVOL
        fi2_str,            # [NEW] Force Index 2-EMA (Column U)
        fi_str,             # [SHIFT] Force Index 13-EMA (Column V)
        ts_str,             # [SHIFT] Trend Strength (Column W)
        vrp_str             # [SHIFT] VRP Spread (Column X)
    ]
    
    try:
        sheet = get_sheet_service()
        
        # [ROBUST APPEND FIX]
        col_dates = sheet.col_values(1)
        # [FIX] Do NOT filter empty strings. 
        # If we filter gaps, we calculate a row index that already exists.
        # len(col_values) returns the index of the last populated cell.
        next_row = len(col_dates) + 1
        
        # Safety
        if next_row < 2: next_row = 2
        
        print(f"📍 TARGET ROW: {next_row} (Total Rows: {len(col_dates)})")
        
        # Explicit Write
        # We assume 24 columns (A to X) based on the row construction above.
        range_str = f"A{next_row}:X{next_row}"
        
        # update(range_name, values) expects a list of lists.
        sheet.update(range_name=range_str, values=[row])
        print(f"✅ SUCCESS: Wrote to Row {next_row} ({range_str})")
        
    except Exception as e:
        print(f"❌ SHEET ERROR: {e}")

    try:
        # [NEW] DUAL-WRITE TO SUPABASE
        print("☁️ Syncing Market Regime to Supabase...")
        
        # Grab the last 50 rows (plus headers) for the Streamlit dashboard
        # This prevents Streamlit from downloading the entire 10,000+ row block
        all_vals = sheet.get_all_values()
        if len(all_vals) > 1:
            headers = all_vals[1] # Row index 1 is Row 2 in Sheets (the real headers)
            tail_vals = all_vals[-50:] if len(all_vals) > 50 else all_vals[2:]
            
            # Construct a dictionary matching the exact Pandas dataframe structure
            payload = {
                "headers": headers,
                "rows": tail_vals
            }
            
            # Fire and forget (don't block the bridge loop)
            asyncio.run(upload_json_to_supabase("nexus_profile", payload, id_field="id", id_value="market_regime"))
            print("✅ SYNCHRONIZED MARKET REGIME WITH SUPABASE")
            
    except Exception as e:
        print(f"❌ SUPABASE SYNC ERROR: {e}")

if __name__ == "__main__":
    print("🔌 NEXUS SHEETS BRIDGE: v2.3 (Supabase Enabled)")
    if len(sys.argv) > 1:
        lbl = sys.argv[1]
        if lbl == "--test-account":
            run_account_dump()
            sys.exit(0)
        elif lbl == "--test-orats":
            run_orats_oi_dump()
            sys.exit(0)
        
        run_update(lbl)
        if lbl != "--loop": sys.exit(0)
    
    # [FIX] Force immediate update on startup so User knows it's alive
    print("🚀 Triggering Startup Update...")
    try:
        run_update("🟢 START UP")
    except Exception as e:
        print(f"⚠️ Startup Update Failed: {e}")
        
    while True:
        now = get_et_now()
        cur_time = now.strftime("%H:%M")
        
        # [FIX] Main Trigger Loop
        if cur_time in TRIGGERS and cur_time != LAST_TRIGGER:
            LAST_TRIGGER = cur_time
            
            # [FIX] Special Handling for 18:00 Account Dump
            if cur_time == "18:00":
                 try: run_account_dump()
                 except Exception as e: print(f"❌ ACCOUNT DUMP ERROR: {e}")
            elif cur_time == "16:30":
                 try: run_orats_oi_dump()
                 except Exception as e: print(f"❌ ORATS OI DUMP ERROR: {e}")
                 
            # Note: Run the 5-Day Ledger analysis at 16:35 specifically to give the
            # ORATS snapshot script above 5 minutes to finish its Google Sheet uploads
            elif cur_time == "16:35":
                 try:
                     import subprocess
                     print("🔥 TRIGGERING 5-DAY FLOW LEDGER PANDAS CALCULATION (16:35)")
                     # [FIX] Run detached using nohup so Pandas dataframe mapping doesn't timeout the bridge thread
                     subprocess.Popen(["nohup", "python3", "/root/update_ledger_sheet.py", "&"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
                     # [NEW] Also independently trigger the SPY 5-Day Flow Ledger
                     subprocess.Popen(["nohup", "python3", "/root/spy_ledger_sheet.py", "&"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=os.setpgrp)
                 except Exception as e:
                     print(f"❌ FLOW LEDGER ERROR: {e}")

            # [FIX] User Request: RESTRICT TO WEEKDAYS (Mon=0, Sun=6)
            # Only run MARKET UPDATE if Mon-Fri (0-4) AND NOT 18:00
            if now.weekday() >= 5:
                # Update Heartbeat anyway so Watchdog doesn't kill it
                pass 
                
            elif cur_time not in ["18:00", "16:30"]:
                # Determine Label
                if cur_time == "10:05": s_name = "🔴 OPEN (10:05)"
                elif cur_time == "13:00": s_name = "🔴 MID (13:00)"
                elif cur_time == "15:45": s_name = "🔴 CLOSE (15:45)"
                elif cur_time == "09:30": s_name = "🔔 BELL (09:30)"
                else: s_name = f"• {cur_time}"
                
                try:
                    run_update(s_name)
                except Exception as e:
                    print(f"❌ CRITICAL UPDATE FAILURE: {e}")
            
        # [FIX] Update Heartbeat File for Nexus Guardian
        try:
            with open("sheets_bridge.log", "w") as f:
                f.write(f"HEARTBEAT: {datetime.datetime.now()}\n")
        except: pass
            
        time.sleep(10)
