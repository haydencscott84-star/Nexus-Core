import requests
import json
import time
import os
import nexus_config

class TradeStationConnector:
    def __init__(self, token_file="ts_tokens.json"):
        self.TOKEN_FILE = token_file
        
        # Dynamic Base URL based on Config
        if getattr(nexus_config, 'LIVE_TRADING', True):
            self.BASE_URL = "https://api.tradestation.com/v3"
            print("[TS] Using LIVE Environment")
        else:
            self.BASE_URL = "https://sim-api.tradestation.com/v3"
            print("[TS] Using SIMULATED Environment")
            
        self.TOKEN_URL = "https://signin.tradestation.com/oauth/token"
        self.CLIENT_ID = nexus_config.TS_CLIENT_ID
        self.CLIENT_SECRET = nexus_config.TS_CLIENT_SECRET
        self.access_token = None
        self.load_tokens()

    def load_tokens(self):
        """Loads tokens from disk."""
        if os.path.exists(self.TOKEN_FILE):
            try:
                with open(self.TOKEN_FILE, 'r') as f:
                    tokens = json.load(f)
                    self.access_token = tokens.get('access_token')
                    return tokens
            except Exception as e:
                print(f"[TS] Error loading tokens: {e}")
        return None

    def save_tokens(self, new_tokens):
        """Saves new tokens to disk, merging with existing ones."""
        try:
            existing = self.load_tokens() or {}
            existing.update(new_tokens)
            
            # Calculate expiry buffer
            if 'expires_in' in new_tokens:
                existing['expires_at'] = time.time() + int(new_tokens['expires_in']) - 60
                
            with open(self.TOKEN_FILE, 'w') as f:
                json.dump(existing, f, indent=4)
            
            self.access_token = existing.get('access_token')
            print("[TS] Tokens refreshed and saved.")
        except Exception as e:
            print(f"[TS] Error saving tokens: {e}")

    def refresh_access_token(self):
        """Refreshes the access token using the refresh token."""
        tokens = self.load_tokens()
        if not tokens or 'refresh_token' not in tokens:
            print("[TS] No refresh token available.")
            return False

        payload = {
            "grant_type": "refresh_token",
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET,
            "refresh_token": tokens['refresh_token']
        }
        
        try:
            r = requests.post(self.TOKEN_URL, data=payload)
            r.raise_for_status()
            new_tokens = r.json()
            self.save_tokens(new_tokens)
            return True
        except Exception as e:
            print(f"[TS] Token Refresh Failed: {e}")
            return False

    def safe_request(self, endpoint, method="GET", params=None, data=None):
        """
        Makes a request with auto-refresh logic on 401.
        """
        url = f"{self.BASE_URL}{endpoint}"
        
        # 1. Try with current token
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            if method == "GET":
                r = requests.get(url, headers=headers, params=params)
            else:
                r = requests.post(url, headers=headers, json=data)
            
            # 2. Handle 401 (Unauthorized)
            if r.status_code == 401:
                print("[TS] 401 Unauthorized. Refreshing token...")
                if self.refresh_access_token():
                    # Retry with new token
                    headers = {"Authorization": f"Bearer {self.access_token}"}
                    if method == "GET":
                        r = requests.get(url, headers=headers, params=params)
                    else:
                        r = requests.post(url, headers=headers, json=data)
                else:
                    print("[TS] Failed to refresh token. Cannot retry.")
                    return None
            
            r.raise_for_status()
            return r.json()
            
        except Exception as e:
            print(f"[TS] Request Error ({endpoint}): {e}")
            return None

    def get_option_chain(self, symbol):
        """
        Fetches option chain using the streaming endpoint (snapshot mode).
        Reads the first valid data message and closes the connection.
        """
        endpoint = f"/marketdata/stream/options/chains/{symbol}"
        url = f"{self.BASE_URL}{endpoint}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        
        try:
            # Use stream=True to handle streaming response
            with requests.get(url, headers=headers, stream=True) as r:
                if r.status_code == 401:
                    print("[TS] 401 on Stream. Refreshing...")
                    if self.refresh_access_token():
                        headers["Authorization"] = f"Bearer {self.access_token}"
                        with requests.get(url, headers=headers, stream=True) as r2:
                            r = r2 # Swap response object
                    else:
                        return []

                r.raise_for_status()
                
                # Read lines until we get data
                for line in r.iter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if "Heartbeat" in data: continue
                            if "Error" in data: 
                                print(f"[TS] Stream Error: {data}")
                                return []
                            
                            # We got data!
                            # TS V3 Stream format for chains usually sends the whole chain or updates?
                            # Let's assume the first message is the snapshot.
                            return self._normalize_chain_data(data)
                        except Exception as e:
                            print(f"[TS] Parse Error: {e}")
                            break
        except Exception as e:
            print(f"[TS] Stream Request Failed: {e}")
        
        return []

    def _normalize_chain_data(self, data):
        """Normalizes TS chain data to our standard format."""
        normalized = []
        # Structure check: TS often returns "Strikes" or a list of options
        # If it's a list of strikes:
        if "Strikes" in data:
            for row in data["Strikes"]:
                strike = float(row.get("StrikePrice", 0))
                expiry = row.get("Expiration", "").split("T")[0] # 2025-11-28T...
                
                # Call
                if "Call" in row:
                    c = row["Call"]
                    normalized.append({
                        "strike": strike, "expiry": expiry, "type": "CALL",
                        "symbol": c.get("Symbol", ""),
                        "bid": float(c.get("Bid", 0) or 0),
                        "ask": float(c.get("Ask", 0) or 0),
                        "delta": float(c.get("Delta", 0) or 0),
                        "volume": int(c.get("Volume", 0) or 0),
                        "open_interest": int(c.get("OpenInterest", 0) or 0),
                        "iv": float(c.get("ImpliedVolatility", 0) or 0) * 100
                    })
                
                # Put
                if "Put" in row:
                    p = row["Put"]
                    normalized.append({
                        "strike": strike, "expiry": expiry, "type": "PUT",
                        "symbol": p.get("Symbol", ""),
                        "bid": float(p.get("Bid", 0) or 0),
                        "ask": float(p.get("Ask", 0) or 0),
                        "delta": float(p.get("Delta", 0) or 0),
                        "volume": int(p.get("Volume", 0) or 0),
                        "open_interest": int(p.get("OpenInterest", 0) or 0),
                        "iv": float(p.get("ImpliedVolatility", 0) or 0) * 100
                    })
                    
        return normalized

    def submit_order(self, account_id, order_payload):
        """
        Submits an order to TradeStation.
        Endpoint: POST /orderexecution/orders
        """
        endpoint = "/orderexecution/orders"
        
        # Ensure AccountID is in payload if not present
        if "AccountID" not in order_payload:
            order_payload["AccountID"] = account_id
            
        print(f"[TS] Submitting Order: {json.dumps(order_payload, indent=2)}")
        
        response = self.safe_request(endpoint, method="POST", data=order_payload)
        
        if response:
            print(f"[TS] Order Response: {response}")
            return response
        else:
            print("[TS] Order Submission Failed.")
            return None

    def fetch_candles(self, symbol, interval="Daily", unit="Day", bars=250):
        """
        Fetches historical candle data from TradeStation.
        Endpoint: /marketdata/barcharts/{symbol}
        """
        endpoint = f"/marketdata/barcharts/{symbol}"
        
        # Map interval to TS API params
        # unit: Minute, Daily, Weekly, Monthly
        params = {
            "unit": unit,
            "interval": interval if unit == "Minute" else 1, # For daily, interval is usually 1
            "barsback": bars,
            "sessiontemplate": "Default" # Changed from USEQ to Default to fix 400 Error
        }
        
        print(f"[TS] Fetching Candles: {symbol} ({bars} {unit}s)...")
        data = self.safe_request(endpoint, params=params)
        
        if not data or "Bars" not in data:
            print(f"[TS] No candle data returned for {symbol}")
            return []
            
        # Normalize to list of dicts
        candles = []
        for b in data["Bars"]:
            candles.append({
                "Date": b.get("TimeStamp"),
                "Open": float(b.get("Open", 0)),
                "High": float(b.get("High", 0)),
                "Low": float(b.get("Low", 0)),
                "Close": float(b.get("Close", 0)),
                "Volume": int(b.get("TotalVolume", 0))
            })
            
        return candles

if __name__ == "__main__":
    ts = TradeStationConnector()
    print("Testing Auth...")
    # Test with a simple quote first
    q = ts.safe_request("/marketdata/quotes/SPY")
    print("Quote:", q)
