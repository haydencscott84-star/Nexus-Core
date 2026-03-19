import os
import tradestation_connector
import orats_connector

class APIManager:
    def __init__(self):
        self.ts_connector = tradestation_connector.TradeStationConnector()
        self.connectors = {
            "TRADESTATION": self.ts_connector,
            "ORATS": orats_connector # Module-based, not class-based
        }
        
    def get_connector(self, source="TRADESTATION"):
        return self.connectors.get(source, self.ts_connector)

    def fetch_chain(self, symbol, source="TRADESTATION"):
        """
        Fetches option chain.
        If source is TRADESTATION and it fails, falls back to ORATS.
        """
        data = []
        
        if source == "TRADESTATION":
            print(f"[API] Attempting fetch from TradeStation...")
            data = self.ts_connector.get_option_chain(symbol)
            
            if not data:
                print(f"[API] TradeStation returned no data. Falling back to ORATS...")
                data = orats_connector.get_live_chain(symbol)
                
        elif source == "ORATS":
            data = orats_connector.get_live_chain(symbol)
            
        return data

    def get_specific_contract_snapshot(self, ticker, expiry, strike, option_type):
        """
        Fetches a specific contract snapshot using ORATS.
        """
        # 1. Fetch Chain (Optimized: Filter by expiry if possible, but ORATS /live/strikes usually takes ticker)
        # We'll fetch the whole chain for the ticker (cached by orats_connector if we used st.cache there? 
        # No, api_manager calls module function. We should probably cache at app level or connector level).
        # For now, just call get_live_chain.
        
        chain = orats_connector.get_live_chain(ticker)
        if chain.empty: return None
        
        # 2. Filter
        # Ensure types match
        strike = float(strike)
        # expiry string format matching? ORATS returns YYYY-MM-DD.
        
        # Filter
        row = chain[
            (chain['expiry'] == expiry) & 
            (chain['strike'] == strike) & 
            (chain['type'] == option_type.upper())
        ]
        
        if not row.empty:
            return row.iloc[0].to_dict()
        return None

    def get_uw_contract_snapshot(self, ticker, expiry, strike, option_type):
        """
        Fetches a specific contract snapshot using Unusual Whales API.
        Endpoint: https://api.unusualwhales.com/api/stock/{ticker}/option-contracts
        """
        import requests
        import os
        
        # Hardcoded key from uw_nexus.py (or load from env/config)
        UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
        
        url = f"https://api.unusualwhales.com/api/stock/{ticker}/option-contracts"
        headers = {"Authorization": f"Bearer {UW_API_KEY}"}
        
        try:
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code != 200:
                print(f"[UW] API Error: {r.status_code}")
                return None
                
            data = r.json()
            # UW returns a list of contracts. We need to filter.
            # Structure: { "data": [ { "strike": ..., "expiry": ..., "option_type": ..., "price": ..., "greeks": {...} } ] }
            # Note: Actual structure might vary. Assuming standard UW response.
            
            contracts = data.get("data", [])
            target_strike = float(strike)
            target_type = option_type.upper() # CALL or PUT
            # UW expiry format? YYYY-MM-DD usually.
            
            for c in contracts:
                # Check Strike
                if float(c.get("strike", 0)) != target_strike: continue
                
                # Check Type (UW might use 'call'/'put' or 'C'/'P')
                c_type = c.get("option_type", "").upper()
                if c_type != target_type and c_type != target_type[0]: continue
                
                # Check Expiry
                if c.get("expiry") != expiry: continue
                
                # Match Found!
                greeks = c.get("greeks", {})
                return {
                    "bid": float(c.get("bid", 0) or 0),
                    "ask": float(c.get("ask", 0) or 0),
                    "last": float(c.get("price", 0) or 0), # 'price' is usually last
                    "delta": float(greeks.get("delta", 0) or 0),
                    "gamma": float(greeks.get("gamma", 0) or 0),
                    "theta": float(greeks.get("theta", 0) or 0),
                    "iv": float(greeks.get("iv", 0) or 0) * 100
                }
                
        except Exception as e:
            print(f"[UW] Fetch Error: {e}")
            
        return None

# Singleton Instance
API_MANAGER = APIManager()
