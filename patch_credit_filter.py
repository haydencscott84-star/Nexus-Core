
SPREADS_FILE = "nexus_spreads_downloaded.py"

# 1. NEW LOGIC: update_positions (Filtering & Labeling)
NEW_UPDATE_POSITIONS = r"""
    def update_positions(self, positions):
        table = self.query_one("#positions_table", DataTable)
        table.clear()
        
        pos_map = {p.get("Symbol"): p for p in positions}
        processed_syms = set()
        
        def parse_sym(s):
            import re
            parts = s.split(' ')
            if len(parts) < 2: return None
            code = parts[1]
            m = re.match(r'^(\d{6})([CP])([\d.]+)$', code)
            if m:
                return {"expiry": m.group(1), "type": m.group(2), "strike": float(m.group(3)), "sym": s}
            return None

        groups = {}
        for sym, p in pos_map.items():
            meta = parse_sym(sym)
            if meta:
                key = f"{meta['expiry']}{meta['type']}"
                if key not in groups: groups[key] = []
                meta["qty"] = float(p.get("Quantity", 0))
                meta["pl"]  = float(p.get("UnrealizedProfitLoss", 0))
                meta["val"] = float(p.get("MarketValue", 0))
                groups[key].append(meta)

        for key, group in groups.items():
            is_call = "C" in key
            shorts = [x for x in group if x["qty"] < 0]
            longs  = [x for x in group if x["qty"] > 0]
            
            for s in shorts:
                if s["sym"] in processed_syms: continue
                match = None
                for l in longs:
                    if l["sym"] in processed_syms: continue
                    is_credit = False
                    if is_call:
                        if s["strike"] < l["strike"]: is_credit = True
                    else:
                        if s["strike"] > l["strike"]: is_credit = True
                    if is_credit:
                        match = l
                        break
                
                if match:
                    l = match
                    qty = abs(int(s["qty"]))
                    pl_net = s["pl"] + l["pl"]
                    val_net = s["val"] + l["val"]
                    type_str = "CALL" if is_call else "PUT"
                    label = f"{type_str} CREDIT ({s['strike']}/{l['strike']})"
                    key_id = f"SPREAD|{s['sym']}|{l['sym']}"
                    table.add_row(label, str(qty), f"${pl_net:.2f}", f"${val_net:.2f}", key=key_id)
                    processed_syms.add(s["sym"])
                    processed_syms.add(l["sym"])
"""

# 2. THREAD SAFETY: account_data_loop
# Wraps query_one.update and call_after_refresh for update_positions
NEW_ACCOUNT_LOOP = r"""
    async def account_data_loop(self):
        while True:
            try:
                topic, msg = await self.acct_sock.recv_multipart()
                import json
                data = json.loads(msg)
                positions = data.get("positions", [])
                
                eq = float(data.get("total_account_value", 0))
                self.account_metrics["equity"] = eq 
                pl = sum([float(p.get("UnrealizedProfitLoss", 0)) for p in positions])
                exp = sum([float(p.get("MarketValue", 0)) for p in positions])
                
                pl_pct = (pl / eq * 100) if eq != 0 else 0.0
                exp_pct = (exp / eq * 100) if eq != 0 else 0.0
                
                def update_acct_ui():
                    try: self.query_one("#acct_display").update(f"P/L: ${pl:.0f} ({pl_pct:+.1f}%) | EXP: ${exp/1000:.1f}K ({exp_pct:.1f}%)")
                    except: pass
                    
                self.call_after_refresh(update_acct_ui)
                self.call_after_refresh(self.update_positions, positions)
            except: pass
"""

# 3. THREAD SAFETY: market_data_loop
NEW_MARKET_LOOP = r"""
    async def market_data_loop(self):
        while True:
            try:
                topic, msg = await self.sub_sock.recv_multipart()
                import json
                data = json.loads(msg)
                if "Last" in data:
                    price = float(data["Last"])
                    self.current_spy_price = price
                    def update_price():
                        try: self.query_one("#spy_price_display").update(f"SPY: {price:.2f}")
                        except: pass
                    self.call_after_refresh(update_price)
            except: pass
"""

# 4. THREAD SAFETY: active_quote_loop
# This one is trickier as it has logic inside. We'll wrap the UI update block.
NEW_QUOTE_LOOP = r"""
    async def active_quote_loop(self):
        while True:
            if self.selected_spread:
                try:
                    short_sym = self.selected_spread["short_sym"]
                    long_sym = self.selected_spread["long_sym"]
                    
                    ctx = zmq.asyncio.Context()
                    sock = ctx.socket(zmq.REQ)
                    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
                    
                    payload = {"cmd": "GET_MULTI_QUOTE", "symbols": [short_sym, long_sym]}
                    await sock.send_json(payload)
                    
                    if await sock.poll(3000):
                        reply = await sock.recv_json()
                        if reply.get("status") == "ok":
                            quotes = reply.get("quotes", {})
                            qs = quotes.get(short_sym)
                            ql = quotes.get(long_sym)
                            
                            if qs and ql:
                                cred_price = qs["Bid"] - ql["Ask"]
                                width = abs(self.selected_spread["short_strike"] - self.selected_spread["long_strike"])
                                risk = (width - cred_price) * 100 * int(self.query_one("#qty_input").value or 1) # Unsafe access? Ideally read from self var, but acceptable for read.
                                equity = self.account_metrics.get("equity", 1)
                                risk_pct = (risk / equity * 100) if equity > 0 else 0
                                yld = (cred_price / width * 100) if width > 0 else 0
                                
                                def update_quote_ui():
                                    try:
                                        self.query_one("#lbl_credit").update(f"${cred_price * 100:.2f} ⚡")
                                        self.query_one("#lbl_risk").update(f"${risk:.2f} ({risk_pct:.1f}%) ⚡")
                                        self.query_one("#lbl_yield").update(f"{yld:.1f}% ⚡")
                                        self.query_one("#lbl_yield").styles.color = "green" if yld > 30 else ("yellow" if yld >= 20 else "red")
                                    except: pass
                                
                                self.call_after_refresh(update_quote_ui)

                    sock.close()
                except: pass
            
            await asyncio.sleep(30)
"""

def patch_file():
    with open(SPREADS_FILE, 'r') as f: content = f.read()
    
    # helper replacement function
    def replace_method(cont, start_sig, end_sig, new_code):
        if start_sig in cont:
            pre, post = cont.split(start_sig, 1)
            if end_sig in post:
                body, remainder = post.split(end_sig, 1)
                print(f"Patched: {start_sig}")
                return pre + new_code.strip() + "\n    \n    " + end_sig + remainder
            else:
                # Fallback for last method if end_sig not found or diff
                # Try indented match
                pass
        print(f"Warning: Could not find {start_sig}")
        return cont

    # 1. Update Positions
    content = replace_method(content, "def update_positions(self, positions):", "async def fetch_managed_spreads_loop(self):", NEW_UPDATE_POSITIONS)
    
    # 2. Account Loop
    content = replace_method(content, "async def account_data_loop(self):", "def update_positions(self, positions):", NEW_ACCOUNT_LOOP)
    
    # 3. Market Loop
    content = replace_method(content, "async def market_data_loop(self):", "def fetch_last_known_price(self):", NEW_MARKET_LOOP)
    
    # 4. Quote Loop
    content = replace_method(content, "async def active_quote_loop(self):", "async def force_refresh_loop(self):", NEW_QUOTE_LOOP)
    
    with open(SPREADS_FILE, 'w') as f: f.write(content)

if __name__ == "__main__":
    patch_file()
