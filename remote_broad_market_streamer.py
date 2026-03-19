import zmq
import json
import time
import os
import requests
import asyncio
import threading
from dotenv import load_dotenv

# Import TradeStation Components
import sys
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except ImportError:
    print("Failed to load TradeStation components.")
    sys.exit(1)

# Load environment variables
load_dotenv(os.path.join(script_dir, '.env'))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ZMQ_PORT_MARKET = 5555

# Tickers to track
ALL_TICKERS_SUB = [b"SPY", b"$SPX.X", b"QQQ", b"IWM", b"$VIX.X", b"@ES", b"@NQ", b"XLK", b"XLF", b"XLV", b"XLY", b"XLP", b"XLE", b"XLC", b"XLI", b"XLB", b"XLRE", b"XLU", b"MESM26"]

# Global Baseline Dictionary
# Populated asynchronously every 60s
ORIGIN_BASELINES = {}

def push_to_supabase(payload):
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing Supabase credentials.")
        return False
        
    url = f"{SUPABASE_URL}/rest/v1/nexus_profile"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    
    data = {
        "id": "broad_market",
        "data": payload
    }
    
    try:
        response = requests.post(url, json=data, headers=headers, timeout=5)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error pushing to Supabase: {e}")
        return False

async def fetch_baselines_loop():
    """
    Background loop that queries the TradeStation Snapshot API
    to cache 'PreviousClose' (Equities) and 'Open' (Futures) values.
    """
    print("Initialize Baseline Fetcher Thread...")
    global ORIGIN_BASELINES
    
    ts = None
    try:
        ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
    except Exception as e:
        print(f"Failed to auth TradeStationManager: {e}")
        return
        
    sym_str = ",".join([s.decode('utf-8') for s in ALL_TICKERS_SUB])
    
    while True:
        try:
            url = f"https://api.tradestation.com/v3/marketdata/quotes/{sym_str}"
            headers = {"Authorization": f"Bearer {ts._get_valid_access_token()}"}
            # Non-blocking requests execution
            r = await asyncio.to_thread(requests.get, url, headers=headers, timeout=10)
            
            if r.status_code == 200:
                quotes = r.json().get("Quotes", [])
                for q in quotes:
                    sym = q.get("Symbol")
                    prev_close = float(q.get("PreviousClose", 0))
                    ts_open = float(q.get("Open", 0))
                    
                    if sym:
                        # Logic: Futures use Open (6 PM Open). Equities use PreviousClose (4 PM Close).
                        # Note: If Open is 0 (rare edge case), fallback to PreviousClose.
                        if sym.startswith("@") or "ESM" in sym or "NQM" in sym:
                            origin = ts_open if ts_open > 0 else prev_close
                        else:
                            origin = prev_close
                            
                        if origin > 0:
                            ORIGIN_BASELINES[sym] = origin
                            
            else:
                print(f"Failed to fetch baselines. API HTTP {r.status_code}")
                
        except Exception as e:
            print(f"Baseline Engine Error: {e}")
            
        await asyncio.sleep(60) # Fetch baselines once per minute

async def async_main():
    print(f"Starting Broad Market Streamer...")
    print(f"Connecting to ZMQ tcp://127.0.0.1:{ZMQ_PORT_MARKET}")
    
    # Start Baseline fetching task
    asyncio.create_task(fetch_baselines_loop())
    
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://127.0.0.1:{ZMQ_PORT_MARKET}")
    
    for ticker in ALL_TICKERS_SUB:
        socket.setsockopt(zmq.SUBSCRIBE, ticker)
        
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    
    price_data = {}
    last_update_time = time.time()
    update_interval = 5.0 # Seconds
    
    print("Listening for ticks...")
    
    try:
        while True:
            # Poll with timeout to allow Supabase interval execution
            socks = dict(poller.poll(100))
            
            if socket in socks:
                try:
                    # Non-blocking receive
                    msg = socket.recv_multipart(flags=zmq.NOBLOCK)
                    sym = msg[0].decode('utf-8')
                    payload = json.loads(msg[1].decode('utf-8'))
                    
                    if "Last" in payload:
                        curr_price = float(payload.get("Last", 0))
                        
                        # --- OVERRIDE MATH LOGIC ---
                        # Rely purely on the Origin Baseline (4 PM Close / 6 PM Open)
                        chg_pct = 0.0
                        origin = ORIGIN_BASELINES.get(sym, 0)
                        if origin > 0 and curr_price > 0:
                            chg_pct = ((curr_price - origin) / origin) * 100
                        else:
                            # Fallback to the stream payload if baseline fails or hasn't loaded yet
                            chg_pct = float(payload.get("NetChangePct", 0))
                            
                        # Preserve unmodified net change from payload, although we focus purely on NetChangePct 
                        net_chg = float(payload.get("NetChange", 0))
                        if origin > 0 and curr_price > 0:
                            net_chg = curr_price - origin
                        
                        price_data[sym] = {
                            "curr": curr_price,
                            "net_chg": net_chg,
                            "chg_pct": chg_pct,
                            "timestamp": time.time()
                        }
                except zmq.Again:
                    pass
                except Exception as e:
                    print(f"Error processing tick: {e}")
            
            # Check if it's time to push to Supabase
            current_time = time.time()
            if current_time - last_update_time >= update_interval:
                if price_data:
                    # Prepare payload
                    payload = {
                        "prices": price_data,
                        "updated_at": current_time
                    }
                    
                    # Push via synchronous blocking call in thread to avoid blocking main tick pump
                    await asyncio.to_thread(push_to_supabase, payload)
                    print(f"[{time.strftime('%H:%M:%S')}] Supabase 'broad_market' updated successfully.")
                    
                last_update_time = current_time
                
    except KeyboardInterrupt:
        print("\nStopping Broad Market Streamer...")
    finally:
        socket.close()
        context.term()

def main():
    asyncio.run(async_main())

if __name__ == "__main__":
    main()
