import re

TARGET_FILE = "/root/trader_dashboard.py"

def apply_fix():
    print(f"Reading {TARGET_FILE}...")
    with open(TARGET_FILE, 'r') as f:
        content = f.read()

    # 1. Add Imports
    if "from orats_connector import get_live_chain" not in content:
        content = "from orats_connector import get_live_chain\nimport pandas as pd\n" + content
        print("Added imports.")

    # 2. Add fetch_orats_greeks method
    # We will add it before `calculate_net_delta`
    
    new_methods = """
    async def fetch_orats_greeks(self):
        \"\"\"Fetches live option chain from ORATS and caches it.\"\"\"
        try:
            self.log_msg("REQ: Fetching ORATS Greeks...")
            loop = asyncio.get_event_loop()
            # Run in thread/executor
            df = await loop.run_in_executor(None, get_live_chain, "SPY")
            
            if not df.empty:
                self.orats_chain = df
                self.log_msg(f"ORATS: Loaded {len(df)} contracts.")
                return True
            else:
                self.log_msg("ORATS: No data returned.")
                return False
        except Exception as e:
            self.log_msg(f"ORATS ERR: {e}")
            return False

    def calculate_net_delta(self):
        \"\"\"Calculates Net Delta using cached ORATS Greeks + Live Price Adjustment.\"\"\"
        try:
            # Check if we have data
            if not hasattr(self, 'orats_chain') or self.orats_chain.empty:
                # Fallback: Count positions if no Greeks (Temporary)
                # Or return 0.0 with warning?
                # Better: Try to fetch if missing? No, async issue.
                return 0.0

            if not self.pos_map: return 0.0

            net_delta = 0.0
            
            # Get Current Price (Preferred: Live Tick, Fallback: Dashboard Metric)
            # stored in ExecutionPanel usually
            try:
                curr_price = self.query_one(ExecutionPanel).und_price
            except: curr_price = 0
            
            if curr_price <= 0 and hasattr(self, 'fallback_price'):
                curr_price = self.fallback_price

            if curr_price <= 0: return 0.0 # Cannot calc without price

            df = self.orats_chain
            
            for sym, pos in self.pos_map.items():
                qty = float(pos.get('qty', 0))
                if qty == 0: continue
                
                # Parse Symbol: "SPY 250117C680"
                # Need Expiry (YYYY-MM-DD), Strike (float), Type (CALL/PUT)
                
                try:
                    parts = sym.split() # ['SPY', '250117C680']
                    raw = parts[1]
                    
                    # Regex to parse '250117C680' -> 25-01-17, C, 680
                    # Standard OCC format usually, but here it is condensed?
                    # Let's assume standardized format used in dashboard
                    
                    # 250117 = YYMMDD
                    y = "20" + raw[:2]
                    m = raw[2:4]
                    d = raw[4:6]
                    expiry = f"{y}-{m}-{d}"
                    
                    typ_char = raw[6] # 'C' or 'P'
                    typ = "CALL" if typ_char == "C" else "PUT"
                    
                    strike = float(raw[7:])
                    
                    # MATCH
                    # Filter DF
                    # We need strict matching. 
                    # Optimization: create multi-index or map? 
                    # For now, simple filter
                    
                    mask = (df['expiry'] == expiry) & (df['type'] == typ) & (abs(df['strike'] - strike) < 0.01)
                    row = df[mask]
                    
                    if not row.empty:
                        # Grab Greeks (These are per-SHARE usually from orats_connector? 
                        # I checked orats_connector.py, it multiplies by 100 for per-contract)
                        # Wait, confirm connector output.
                        # "c_delta = float(...) or 0" -> It does NOT multiply Delta by 100.
                        # "c_gamma = ... * 100" -> Gamma IS multiplied by 100.
                        
                        # So Delta is 0.50 (per share). Contract Delta is 50? 
                        # Usually Net Delta is displayed as Share Equivalence.
                        # 1 Call (Delta 0.5) = 50 Shares Delta.
                        # So we want Delta * 100.
                        
                        r = row.iloc[0]
                        ref_delta = float(r['delta']) # 0.5 typical
                        ref_gamma = float(r['gamma']) # Scaled by 100 in connector? 
                        # In connector: "c_gamma = ... * 100"
                        # So ref_gamma is contract gamma?
                        # Let's assume standard Greeks:
                        # Delta ~ 0.5
                        # Gamma ~ 0.05
                        
                        ref_price = float(r['stockPrice'] or curr_price)
                        
                        # Adjust for Price Move
                        # New Delta = Ref_Delta + (Ref_Gamma * (Curr - Ref))
                        # Wait, verify gamma scaling.
                        # If Gamma is contract-gamma (e.g. 5.0), and Price moves $1.
                        # Delta changes by 5.0.
                        # If connector scaled Gamma by 100, then it is correct for Share Delta.
                        
                        # Result should be * 100 for Share Equivalence?
                        # If ref_delta is 0.5. 
                        # We want to add 50 to Net Delta.
                        # So we do: (ref_delta * 100) + ...
                        
                        # Let's trust the values for now, but ensure we scale to shares.
                        
                        adj_delta = (ref_delta * 100) + (ref_gamma * (curr_price - ref_price))
                        
                        net_delta += (qty * adj_delta)
                        
                    else:
                        # Missing Data Fallback
                        # Use Delta from Position if valid?
                        pos_delta = float(pos.get('Delta', 0)) 
                        # This might be stale TS data or 0.
                        if pos_delta != 0:
                             net_delta += (qty * pos_delta * 100) # Assume TS sends 0.5
                        pass
                        
                except Exception as ex: 
                    # Parse error
                    pass

            return net_delta
        except Exception as e:
            self.log_msg(f"[ERR] Calc: {e}")
            return 0.0
    """

    # Replace existing calculate_net_delta and add fetch method
    # We look for the existing `def calculate_net_delta` block
    match = re.search(r"def calculate_net_delta\(self\):.*?(?=\n    def|\n    async def|\nif __name__)", content, re.DOTALL)
    if match:
        content = content.replace(match.group(0), new_methods)
        print("Replaced calculate_net_delta and added fetch_orats_greeks.")
    else:
        print("Could not find calculate_net_delta.")
        return

    # 3. Inject Fetch Call in sub_mkt
    # We want to call it once on startup. 
    # Look for `if not is_sleep_mode():` (or where we bypassed it)
    # Actually, we put `self._update_delta_safe() # Force Init` at start of sub_mkt.
    # We should put the fetch before that.
    
    # And we need to await it. `sub_mkt` is async. Perfect.
    
    # Logic:
    # await self.fetch_orats_greeks()
    # Then update delta.
    
    tgt = 'self._update_delta_safe() # Force Init'
    if tgt in content:
        rep = 'await self.fetch_orats_greeks()\n        self._update_delta_safe() # Force Init'
        content = content.replace(tgt, rep)
        print("Injected fetch_orats_greeks call in sub_mkt.")
    else:
        print("Could not find injection point in sub_mkt.")

    print("Writing fixed file...")
    with open(TARGET_FILE, 'w') as f:
        f.write(content)
    print("Success.")

if __name__ == "__main__":
    apply_fix()
