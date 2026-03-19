
import os

SOURCE = "ts_nexus.py"
DEST = "ts_nexus_patched.py"

NEW_IMPORTS = "import mibian\nimport math\n"

# The entire new method
FETCH_METHOD_CODE = """    async def fetch_option_chain(self, ticker, target_strike, width, type_, raw=False):
        \"\"\"
        Fetches option chain.
        If raw=True: Returns list of individual options with Delta (Mibian).
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
                self.log_msg(f"DEBUG: Expirations API Failed: {r.status_code} {r.text}")
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
                
                # RAW MODE: Iterate Strikes around Target (For Debit/Custom Scans)
                if raw:
                    # Fetch reasonable range of strikes (e.g. +/- 10%)
                    center = float(target_strike) if target_strike else spot_price
                    if not center: center = 500 # Fallback
                    
                    # Fetch ALL strikes for expiry (Optimized: Filter locally)
                    url_s = f"{self.TS.BASE_URL}/marketdata/options/strikes/{ticker}?expiration={expiry_date}"
                    r_s = await asyncio.to_thread(requests.get, url_s, headers=headers)
                    strikes_data = r_s.json().get("Strikes", [])
                    
                    # Filter: +/- 75 points (Wider for SPY)
                    valid_strikes = []
                    for s_row in strikes_data:
                        try:
                            val = float(s_row[0])
                            if abs(val - center) < 75: 
                                valid_strikes.append(val)
                        except: pass
                        
                    # Build Symbols
                    symbols = []
                    exp_fmt = exp_dt.strftime("%y%m%d")
                    for s in valid_strikes:
                        s_str = f"{int(s)}" if s == int(s) else f"{s}"
                        if type_ == "CALL":
                            symbols.append(f"{ticker} {exp_fmt}C{s_str}")
                        elif type_ == "PUT":
                            symbols.append(f"{ticker} {exp_fmt}P{s_str}")
                    
                    # Batch Fetch Quotes (Chunking 20)
                    chunk_size = 20
                    for i in range(0, len(symbols), chunk_size):
                        chunk = symbols[i:i+chunk_size]
                        q_url = f"{self.TS.BASE_URL}/marketdata/quotes/{','.join(chunk)}"
                        r_q = await asyncio.to_thread(requests.get, q_url, headers=headers)
                        if r_q.status_code == 200:
                            quotes = r_q.json().get("Quotes", [])
                            for q in quotes:
                                try:
                                    sym = q["Symbol"]
                                    strike_part = sym.split(type_[0])[-1]
                                    strike_val = float(strike_part)
                                    
                                    bid = float(q.get("Bid", 0))
                                    ask = float(q.get("Ask", 0))
                                    
                                    # Calculate Delta (Mibian)
                                    iv = 20.0 
                                    delta = 0.0
                                    try:
                                        if spot_price > 0:
                                            # Interest ~ 4.5%
                                            c = mibian.BS([spot_price, strike_val, 4.5, dte], volatility=iv)
                                            if type_ == "CALL": delta = c.callDelta
                                            else: delta = c.putDelta
                                    except: pass
                                    
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
                                except Exception: pass
                                    
                # LEGACY MODE (Vertical Spreads - Credit Only)
                else: 
                    url_s = f"{self.TS.BASE_URL}/marketdata/options/strikes/{ticker}?expiration={expiry_date}"
                    r_s = await asyncio.to_thread(requests.get, url_s, headers=headers)
                    strikes = r_s.json().get("Strikes", [])
                    strikes = [float(s[0]) for s in strikes]
                    
                    short_strike = float(target_strike)
                    long_strike = short_strike - float(width) if type_ == "PUT" else short_strike + float(width)
                    
                    exp_fmt = exp_dt.strftime("%y%m%d")
                    def make_sym(s):
                        s_str = f"{int(s)}" if s == int(s) else f"{s}"
                        return f"{ticker} {exp_fmt}{type_[0]}{s_str}"

                    short_sym = make_sym(short_strike)
                    long_sym = make_sym(long_strike)
                    
                    quotes_url = f"{self.TS.BASE_URL}/marketdata/quotes/{short_sym},{long_sym}"
                    r_q = await asyncio.to_thread(requests.get, quotes_url, headers=headers)
                    if r_q.status_code == 200:
                        qs = r_q.json().get("Quotes", [])
                        q_short = next((q for q in qs if q["Symbol"] == short_sym), {})
                        q_long = next((q for q in qs if q["Symbol"] == long_sym), {})
                        
                        if q_short and q_long:
                            bid_short = float(q_short.get("Bid", 0))
                            ask_long = float(q_long.get("Ask", 0))
                            credit = bid_short - ask_long
                            risk = float(width) - credit
                            rr = (credit / risk) * 100 if risk > 0 else 0
                            breakeven = short_strike - credit if type_ == "PUT" else short_strike + credit
                            
                            results.append({
                                "expiry": expiry_date,
                                "dte": dte,
                                "short": short_strike,
                                "long": long_strike,
                                "credit": round(credit, 2),
                                "risk": round(risk, 2),
                                "rr": round(rr, 1),
                                "breakeven": round(breakeven, 2),
                                "short_sym": short_sym,
                                "long_sym": long_sym
                            })
            return results
"""

OLD_CMD_LINE = "data = await self.fetch_option_chain(ticker, strike, width, type_)"
NEW_CMD_LINE = "                    raw = msg.get('raw', False)\n                    data = await self.fetch_option_chain(ticker, strike, width, type_, raw=raw)"

with open(SOURCE, 'r') as f:
    lines = f.readlines()

# 1. Sanitize (Remove SSH Spawn Lines)
start_idx = 0
for i, line in enumerate(lines):
    if line.startswith("#"):
        start_idx = i
        break
    if "import" in line:
        start_idx = i
        break

clean_lines = lines[start_idx:]
full_text = "".join(clean_lines)

# 2. Inject Imports
# Find last import
import_idx = full_text.find("import requests")
if import_idx != -1:
    full_text = full_text[:import_idx] + NEW_IMPORTS + full_text[import_idx:]
else:
    full_text = NEW_IMPORTS + full_text

# 3. Update Command Handler
if OLD_CMD_LINE in full_text:
    full_text = full_text.replace(OLD_CMD_LINE, NEW_CMD_LINE)
else:
    print("WARNING: Could not find OLD_CMD_LINE to replace!")

# 4. Replace Method
# We need to find the start of the old method and the start of the next method.
method_start = "async def fetch_option_chain(self, ticker, target_strike, width, type_):"
next_method_start = "async def execute_spread"

start_pos = full_text.find(method_start)
end_pos = full_text.find(next_method_start)

if start_pos != -1 and end_pos != -1:
    # We replace from start_pos up to (but not including) end_pos
    # We need to be careful about indentation.
    # The new method code string is already indented with 4 spaces.
    
    # Check if there is trailing whitespace before next method
    # Usually methods in classes are separated by blank lines.
    
    new_text = full_text[:start_pos] + FETCH_METHOD_CODE + "\n\n    " + full_text[end_pos:]
    full_text = new_text
    print("Replaced fetch_option_chain method.")
else:
    print("WARNING: Could not identify method boundaries.")

with open(DEST, 'w') as f:
    f.write(full_text)

print(f"Patched file written to {DEST}")
