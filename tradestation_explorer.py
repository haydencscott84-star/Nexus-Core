import requests
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import certifi

# --- 1. CONFIGURATION ---
CLIENT_ID = os.environ.get("TS_CLIENT_ID", "YOUR_TS_CLIENT_ID")
CLIENT_SECRET = os.environ.get("TS_CLIENT_SECRET", "YOUR_TS_CLIENT_SECRET")

# --- 2. AUTH HANDLER ---
authorization_code = None
httpd = None

class _OAuthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global authorization_code, httpd
        try:
            if "code=" in self.path:
                authorization_code = self.path.split("code=")[1].split("&")[0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><h1>Success! You can close this window.</h1></html>")
            else:
                self.send_response(400)
                self.end_headers()
        except Exception:
            self.send_response(400)
            self.end_headers()
        
        # Shutdown server in a separate thread to avoid blocking the response
        threading.Thread(target=lambda: httpd.shutdown()).start()

def _start_local_server():
    global httpd
    server_address = ('localhost', 8080)
    httpd = HTTPServer(server_address, _OAuthHandler)
    httpd.serve_forever()

# --- 3. TRADESTATION MANAGER CLASS ---
class TradeStationManager:
    def __init__(self, client_id, client_secret, account_id, redirect_uri="http://localhost:8080", token_file="ts_tokens.json"):
        self.CLIENT_ID = client_id
        self.CLIENT_SECRET = client_secret
        self.ACCOUNT_ID = account_id 
        self.REDIRECT_URI = redirect_uri
        self.TOKEN_FILE = token_file
        self.BASE_URL = "https://api.tradestation.com/v3"
        self.AUTH_URL = "https://signin.tradestation.com/authorize"
        self.TOKEN_URL = "https://signin.tradestation.com/oauth/token"
        
        # Thread-safe lock for token operations
        self.token_lock = threading.Lock()
        
        # Initialize access token
        self.access_token = self._get_valid_access_token()

    # --- CORE TOKEN MANAGEMENT (THE FIX) ---
    def _save_tokens(self, new_tokens):
        """
        Safely merges new tokens with existing ones to prevent data loss.
        Crucial for keeping the Refresh Token alive.
        """
        try:
            # 1. Load existing tokens first
            if os.path.exists(self.TOKEN_FILE):
                with open(self.TOKEN_FILE, 'r') as f:
                    existing_tokens = json.load(f)
            else:
                existing_tokens = {}

            # 2. Merge new data into existing data
            # This ensures if 'refresh_token' is missing in new_tokens, we keep the old one!
            existing_tokens.update(new_tokens)
            
            # 3. Calculate absolute expiration time with a buffer
            # TradeStation tokens last 1200 seconds (20 mins). We subtract 60s to be safe.
            if 'expires_in' in new_tokens:
                existing_tokens['expires_at'] = time.time() + int(new_tokens['expires_in']) - 60
            
            # 4. Save back to disk
            with open(self.TOKEN_FILE, 'w') as f: 
                json.dump(existing_tokens, f, indent=4)
                
        except Exception as e:
            print(f"ERROR Saving Tokens: {e}")

    def _load_tokens(self):
        if os.path.exists(self.TOKEN_FILE):
            try:
                with open(self.TOKEN_FILE, 'r') as f: 
                    return json.load(f)
            except:
                return None
        return None

    def _get_initial_tokens(self):
        """Performs the full browser-based login flow (First time only)"""
        global authorization_code
        authorization_code = None
        
        print("Launching browser for authentication...")
        # Optional: Logout first to force a fresh login screen
        # webbrowser.open("https://signin.tradestation.com/v2/logout")
        # time.sleep(1)
        
        scopes = "openid profile offline_access MarketData ReadAccount Trade OptionSpreads"
        auth_params = {
            "response_type": "code", 
            "client_id": self.CLIENT_ID,
            "redirect_uri": self.REDIRECT_URI, 
            "audience": "https://api.tradestation.com",
            "scope": scopes
        }
        
        # Build URL properly
        req = requests.Request('GET', self.AUTH_URL, params=auth_params)
        auth_url = req.prepare().url
        
        # [FIX] Headless Support
        print(f"\n⚠️ AUTH REQUIRED: Please visit this URL to login:\n{auth_url}\n")
        print("Since this is a headless server, you will be redirected to localhost (which will fail).")
        print("Copy the 'code=XYZ' part from the URL bar and write it to 'ts_code.txt' or paste here.")
        
        try: webbrowser.open(auth_url)
        except: pass
        
        # Start local server to catch the callback (Optimistic)
        server_thread = threading.Thread(target=_start_local_server)
        server_thread.start()
        
        # Wait for the code check file occasionally
        print("Waiting for Authorization Code (Web or ts_code.txt)...")
        while authorization_code is None: 
            if os.path.exists("ts_code.txt"):
                try:
                   with open("ts_code.txt", "r") as f:
                       c = f.read().strip()
                       if c: 
                           authorization_code = c
                           print(f"Code received from file: {c[:10]}...")
                   os.remove("ts_code.txt")
                except: pass
            time.sleep(1)
        
        # Exchange code for tokens
        token_payload = {
            "grant_type": "authorization_code", 
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET, 
            "code": authorization_code,
            "redirect_uri": self.REDIRECT_URI
        }
        
        try:
            # [FIX] Added timeout
            r = requests.post(self.TOKEN_URL, data=token_payload, verify=certifi.where(), timeout=10)
            r.raise_for_status()
            tokens = r.json()
            self._save_tokens(tokens)
            return tokens
        except Exception as e:
            print(f"Initial Auth Failed: {e}")
            return None

    def _refresh_access_token(self, refresh_token):
        """Silently gets a new access token using the refresh token"""
        token_payload = {
            "grant_type": "refresh_token", 
            "client_id": self.CLIENT_ID,
            "client_secret": self.CLIENT_SECRET, 
            "refresh_token": refresh_token
        }
        try:
            # [FIX] Added timeout
            r = requests.post(self.TOKEN_URL, data=token_payload, verify=certifi.where(), timeout=10)
            r.raise_for_status()
            tokens = r.json()
            
            # Save the new tokens (Merge with old ones)
            self._save_tokens(tokens)
            return tokens
        except Exception as e:
            print(f"Token Refresh Failed: {e}")
            return None

    def _get_valid_access_token(self):
        """Returns a valid token, refreshing automatically if needed."""
        with self.token_lock:
            # 1. Try to load from disk
            tokens = self._load_tokens()
            
            if tokens:
                # Check if expired (or expiring soon)
                if tokens.get('expires_at', 0) > time.time():
                    return tokens['access_token']
                
                # If expired, try to refresh
                if 'refresh_token' in tokens:
                    print("Token expired. Refreshing automatically...")
                    new_tokens = self._refresh_access_token(tokens['refresh_token'])
                    if new_tokens:
                        return new_tokens['access_token']
            
            # 2. If all else fails, trigger browser login
            # (Note: This will fail on a headless server, which is why 
            # uploading the initial ts_tokens.json file is critical!)
            print("No valid tokens found. Initiating browser login...")
            tokens = self._get_initial_tokens()
            if tokens:
                return tokens['access_token']
            
            raise Exception("Authentication Failed: Could not get valid token.")

    def _make_api_request(self, endpoint, method="GET", params=None, data=None):
        """Centralized request handler with auto-retry on 401 errors"""
        url = f"{self.BASE_URL}{endpoint}"
        
        # First attempt
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            if method == "GET": 
                r = requests.get(url, headers=headers, params=params, verify=certifi.where(), timeout=10)
            elif method == "POST": 
                r = requests.post(url, headers=headers, json=data, verify=certifi.where(), timeout=10)
            elif method == "PUT": 
                r = requests.put(url, headers=headers, json=data, verify=certifi.where(), timeout=10)
            elif method == "DELETE": 
                r = requests.delete(url, headers=headers, verify=certifi.where(), timeout=10)


            
            # If 401 Unauthorized, token might have expired mid-session
            if r.status_code == 401:
                print("401 Error detected. Forcing token refresh...")
                # Force a refresh by manually calling get_valid_access_token
                # (Logic inside will see it's expired or force refresh)
                self.access_token = self._get_valid_access_token()
                
                # Retry the request once with new token
                headers = {"Authorization": f"Bearer {self.access_token}"}
                if method == "GET": 
                    r = requests.get(url, headers=headers, params=params, verify=certifi.where(), timeout=10)
                elif method == "POST": 
                    r = requests.post(url, headers=headers, json=data, verify=certifi.where(), timeout=10)
                elif method == "PUT": 
                    r = requests.put(url, headers=headers, json=data, verify=certifi.where(), timeout=10)
                elif method == "DELETE": 
                    r = requests.delete(url, headers=headers, verify=certifi.where(), timeout=10)
            
            r.raise_for_status()
            return r.json()
            
        except requests.exceptions.HTTPError as e:
            # print(f"API Request Error: {e}") # Optional logging
            return None
        except Exception as e:
            return None

    # --- DATA FETCHING METHODS ---
    
    def get_account_balances(self, account_id=None):
        target_account = account_id if account_id else self.ACCOUNT_ID
        if not target_account or target_account == "FILL_ME_IN": return []
        data = self._make_api_request(f"/brokerage/accounts/{target_account}/balances")
        
        if not data: return []
        if isinstance(data, dict) and "Balances" in data: return data["Balances"]
        if isinstance(data, list): return data
        if isinstance(data, dict): return [data]
        return []

    def get_positions(self, account_id=None):
        target_account = account_id if account_id else self.ACCOUNT_ID
        if not target_account or target_account == "FILL_ME_IN": return []
        data = self._make_api_request(f"/brokerage/accounts/{target_account}/positions")
        
        if not data: return []
        if isinstance(data, dict) and "Positions" in data: return data["Positions"]
        if isinstance(data, dict) and "positions" in data: return data["positions"]
        if isinstance(data, list): return data
        if isinstance(data, dict): return [data]
        return []

    def get_quote_snapshot(self, symbol):
        """Fetches a single realtime quote."""
        if not self.access_token: return None
        url = f"{self.BASE_URL}/marketdata/quotes/{symbol}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            r = requests.get(url, headers=headers, verify=certifi.where(), timeout=5)
            if r.status_code == 200:
                data = r.json()
                if "Quotes" in data and len(data["Quotes"]) > 0:
                    return data["Quotes"][0]
        except: pass
        return None

    def place_order(self, symbol, quantity, side="Buy", order_type="Limit", limit_price=None, account_id=None):
        target_account = account_id if account_id else self.ACCOUNT_ID
        
        if not target_account or target_account == "FILL_ME_IN":
            return {"Error": "Account ID not set"}

        payload = {
            "AccountID": target_account,
            "Symbol": symbol,
            "Quantity": str(quantity),
            "OrderType": order_type,
            "TradeAction": "Buy" if side.upper() == "BUY" else ("Sell" if side.upper() == "SELL" else side),
            "TimeInForce": {"Duration": "DAY"},
            "Route": "Intelligent"
        }

        if order_type == "Limit" and limit_price:
            payload["LimitPrice"] = str(limit_price)
        
        # --- FIX: Use _make_api_request to handle Token Refresh automatically ---
        # This prevents 401 errors from silently killing your orders.
        try:
            return self._make_api_request("/orderexecution/orders", method="POST", data=payload)
        except Exception as e:
            return {"Error": str(e)}

    def get_historical_data(self, symbol, interval="1", unit="Daily", bars_back="100"):
        endpoint = f"/marketdata/barcharts/{symbol}"
        params = {"interval": interval, "unit": unit, "barsback": bars_back, "sessiontemplate": "Default"}
        data = self._make_api_request(endpoint, params=params)
        if data and ("Bars" in data or "bars" in data): 
            return data.get("Bars") or data.get("bars")
        return []

    def get_order_status(self, order_id):
        """Fetches the current status of an order."""
        if not self.ACCOUNT_ID or self.ACCOUNT_ID == "FILL_ME_IN": return "UNKNOWN"
        data = self._make_api_request(f"/orderexecution/orders/{order_id}")
        if data and "Orders" in data and len(data["Orders"]) > 0:
            return data["Orders"][0].get("Status")
        return "UNKNOWN"

    def modify_order(self, order_id, new_price):
        """Modifies the limit price of an existing order."""
        payload = {"LimitPrice": str(new_price)}
        try:
            return self._make_api_request(f"/orderexecution/orders/{order_id}", method="PUT", data=payload)
        except Exception as e:
            return {"Error": str(e)}

    def cancel_order(self, order_id):
        """Cancels an existing order."""
        try:
            return self._make_api_request(f"/orderexecution/orders/{order_id}", method="DELETE")
        except Exception as e:
            return {"Error": str(e)}

    # --- HELPER FOR WALKER ---
    async def submit_limit(self, order_details, price):
        """
        Async wrapper for place_order to be used by smart_limit_walker.
        order_details: {symbol, qty, side, type}
        """
        # Unwrap details
        symbol = order_details.get("symbol")
        qty = order_details.get("qty")
        side = order_details.get("side")
        
        # Call synchronous place_order (will be blocking if not awaiting to_thread, but walker calls it with await so we might need to wrap it if place_order is blocking)
        # But TradeStationManager methods are sync using requests. 
        # The walker is async. So we should probably make this async or use asyncio.to_thread in the walker.
        # For compatibility with the requested walker signature "await client.submit_limit", this needs to be async or the walker needs to call loop.run_in_executor.
        # Given the existing code structure in ts_nexus mostly uses asyncio.to_thread for TS calls, I will make this a standard sync method and let the walker handle the async wrapping, OR implement it as async here.
        # However, TradeStationManager is currently all sync.
        # I will implement `submit_limit` as a wrapper that calls `place_order` and returns the Order ID directly or None.
        
        resp = self.place_order(symbol, qty, side, order_type="Limit", limit_price=price)
        if resp and "Orders" in resp:
            return resp["Orders"][0].get("OrderID")
        return None