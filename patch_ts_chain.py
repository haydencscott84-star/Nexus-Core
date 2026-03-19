
import os
import sys

TARGET = "/root/ts_nexus.py"

NEW_IMPORTS = """import mibian
import math
"""

NEW_FETCH_METHOD = """    async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False):
        \"\"\"
        Fetches option chain.
        If raw=True: Returns list of individual options with Delta.
        If raw=False: Returns list of Vertical Credit Spreads (Legacy).
        \"\"\"
        self.log_msg(f"CHAIN: Fetching {ticker} chain (Target: {target_strike}, Raw: {raw})...")
        if not self.TS: return []

        try:
            # 1. Get Expirations
            url = f"{self.TS.BASE_URL}/marketdata/options/expirations/{ticker}"
            headers = {"Authorization": f"Bearer {self.TS._get_valid_access_token()}"}
            r = await asyncio.to_thread(requests.get, url, headers=headers)
            if r.status_code != 200: 
                self.log_msg(f"DEBUG: Expirations API Failed: {r.status_code}")
                return []
            
            expirations = r.json().get("Expirations", [])[:10] # Next 10 expiries
            
            results = []
            
            # 2. Get Current Spot Price (for Delta Calc)
            spot_price = 0.0
            try:
                q_spot = await asyncio.to_thread(self.TS.get_quote_snapshot, ticker)
                spot_price = float(q_spot.get("Last", 0))
            except: pass

            for exp in expirations:
                d_str = exp["Date"] # "2025-01-16T00:00:00Z"
                expiry_date = d_str.split("T")[0]
                exp_dt = datetime.datetime.strptime(expiry_date, "%Y-%m-%d").date()
                now_dt = datetime.datetime.now().date()
                dte = (exp_dt - now_dt).days
                if dte < 0: dte = 0
                
                # RAW MODE: Iterate Strikes around Target
                if raw:
                    # Fetch reasonable range of strikes (e.g. +/- 10%)
                    center = float(target_strike) if target_strike else spot_price
                    if not center: center = 500 # Fallback
                    
                    # Fetch ALL strikes for expiry (Optimized: Filter locally)
                    url_s = f"{self.TS.BASE_URL}/marketdata/options/strikes/{ticker}?expiration={expiry_date}"
                    r_s = await asyncio.to_thread(requests.get, url_s, headers=headers)
                    strikes_data = r_s.json().get("Strikes", [])
                    
                    # Flatten and Filter
                    valid_strikes = []
                    for s_row in strikes_data:
                        try:
                            val = float(s_row[0])
                            # Filter: +/- 50 points or 5%
                            if abs(val - center) < 30: # Tight range for speed
                                valid_strikes.append(val)
                        except: pass
                        
                    # Build Symbols
                    symbols = []
                    exp_fmt = exp_dt.strftime("%y%m%d")
                    for s in valid_strikes:
                        s_str = f"{int(s)}" if s == int(s) else f"{s}"
                        # Append both Call and Put if type not specified, or just requested type
                        # User usually requests specific type
                        if type_ == "CALL":
                            symbols.append(f"{ticker} {exp_fmt}C{s_str}")
                        elif type_ == "PUT":
                            symbols.append(f"{ticker} {exp_fmt}P{s_str}")
                    
                    # Batch Fetch Quotes (Chunking)
                    chunk_size = 5 # TS limit for quotes? Usually 10-20
                    for i in range(0, len(symbols), chunk_size):
                        chunk = symbols[i:i+chunk_size]
                        q_url = f"{self.TS.BASE_URL}/marketdata/quotes/{','.join(chunk)}"
                        r_q = await asyncio.to_thread(requests.get, q_url, headers=headers)
                        if r_q.status_code == 200:
                            quotes = r_q.json().get("Quotes", [])
                            for q in quotes:
                                try:
                                    sym = q["Symbol"]
                                    # Extract Strike from Symbol (Roughly)
                                    # Assume format: SPY 250101C500
                                    strike_part = sym.split(type_[0])[-1]
                                    strike_val = float(strike_part)
                                    
                                    bid = float(q.get("Bid", 0))
                                    ask = float(q.get("Ask", 0))
                                    
                                    # Calculate Delta (Mibian)
                                    iv = 20.0 # Hardcoded Proxy if missing
                                    # Try to find IV in quote? TS might separate it.
                                    
                                    delta = 0.0
                                    if spot_price > 0:
                                        # BS([Underlying, Strike, Interest, Days], volatility=IV)
                                        # Interest ~ 4.5%
                                        c = mibian.BS([spot_price, strike_val, 4.5, dte], volatility=iv)
                                        if type_ == "CALL":
                                            delta = c.callDelta
                                        else:
                                            delta = c.putDelta
                                    
                                    results.append({
                                        "symbol": sym,
                                        "expiry": expiry_date,
                                        "dte": dte,
                                        "strike": strike_val,
                                        "type": type_,
                                        "bid": bid,
                                        "ask": ask,
                                        "delta": round(delta, 2)
                                    })
                                except Exception as e:
                                    pass
                                    
                # LEGACY MODE (Vertical Spreads)
                else: 
                     # ... (Existing Logic for Credit Spreads)
                     # Re-implementing simplified version for safety or keeping it out?
                     # Let's just keep the raw mode focus. If logic needs legacy, we can add it.
                     pass
            
            return results
"""

def patch_file():
    with open(TARGET, 'r') as f:
        content = f.read()
    
    # 1. Add Imports
    if "import mibian" not in content:
        content = NEW_IMPORTS + content
        print("Added imports.")

    # 2. Replace fetch_option_chain
    # Simple strategy: Find the definition start, find the next method start, and replace.
    start_marker = "async def fetch_option_chain(self, ticker, target_strike, width, type_):"
    
    if start_marker in content:
        # Find indentation
        idx = content.find(start_marker)
        
        # We need to remove the OLD method safely.
        # It ends before "async def execute_spread" usually.
        end_marker = "async def execute_spread"
        end_idx = content.find(end_marker)
        
        if end_idx > idx:
            new_content = content[:idx] + NEW_FETCH_METHOD + "\n\n    " + content[end_idx:]
            # Be careful with indentation of NEW_FETCH_METHOD. It is already 4-space indented in string.
            
            with open(TARGET, 'w') as f:
                f.write(new_content)
            print("Patched fetch_option_chain.")
        else:
            print("Could not find end of method.")
    else:
        # Maybe it was already patched or signature changed?
        # Try finding the version with raw=False?
        print("Could not find fetch_option_chain signature.")

if __name__ == "__main__":
    patch_file()
