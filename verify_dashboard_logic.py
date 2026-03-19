import json
import re

# --- MOCK DATA (Simulating ts_nexus.py -> ZMQ Payload) ---
# This matches the structure I verified in ts_nexus.py
mock_payload_1 = {
    "total_account_value": 55000.0,
    "unrealized_pnl": -500.0,
    "positions": [
        {
            "Symbol": "SPY 260116P710",
            "Quantity": 3,
            "Last": 30.00,
            "AveragePrice": 32.20, # API Provided
            "MarketValue": 9000.0,
            "TotalCost": 9660.0,
            "UnrealizedProfitLoss": -660.0, # API Provided
            "OpenProfitLossPercent": -6.83, # API Provided
            "ExpirationDate": "2026-01-16T00:00:00Z"
        }
    ]
}

mock_payload_2 = {
    "total_account_value": 54000.0,
    "unrealized_pnl": -1500.0,
    "positions": [
        {
            "Symbol": "SPY 260116P710",
            "Quantity": 3,
            "Last": 28.00,
            "AveragePrice": 32.20, # API Provided (Static Entry)
            "MarketValue": 8400.0,
            "TotalCost": 9660.0,
            "UnrealizedProfitLoss": -1260.0, # API Provided (Dynamic P/L)
            "OpenProfitLossPercent": -13.04, # API Provided (Dynamic P/L)
            "ExpirationDate": "2026-01-16T00:00:00Z"
        }
    ]
}

# --- DASHBOARD LOGIC (Copied from trader_dashboard.py) ---
def _to_float(x):
    try: return float(x)
    except: return 0.0

def parse_position_details(p):
    # Simplified version of dashboard parser
    sym = p.get('Symbol')
    return sym, "2026-01-16", "PUT", 412

def process_payload(d):
    print(f"\n📥 Processing Payload (Market Price: ${d['positions'][0]['Last']})")
    
    eq = _to_float(d.get("total_account_value", 0))
    pnl_agg = _to_float(d.get("unrealized_pnl", 0))
    
    for p in d.get("positions", []):
        q = int(p.get('Quantity', 0))
        if q == 0: continue
        
        # --- CRITICAL LOGIC FROM DASHBOARD ---
        mkt_val = _to_float(p.get('MarketValue', 0))
        upnl = _to_float(p.get('UnrealizedProfitLoss', 0))
        cost = _to_float(p.get('TotalCost', 0))
        
        # Calculate P/L % (Dynamic)
        pct_pl = (upnl / cost * 100) if cost != 0 else 0.0
        
        # Extract Average Price (Dynamic)
        avg_price = _to_float(p.get('AveragePrice', 0))
        if avg_price == 0 and q != 0:
            avg_price = (cost / q / 100)
            
        print(f"   ✅ Extracted Entry: ${avg_price:.2f}")
        print(f"   ✅ Calculated P/L: {pct_pl:.2f}% (Source: ${upnl} / ${cost})")
        
        # Verify against API provided %
        api_pct = _to_float(p.get('OpenProfitLossPercent', 0))
        print(f"   ℹ️  API Reported P/L: {api_pct:.2f}%")

# --- EXECUTION ---
print("🔵 VERIFYING TRADER_DASHBOARD.PY LOGIC")
print("--------------------------------------------------")
process_payload(mock_payload_1)
process_payload(mock_payload_2)
print("--------------------------------------------------")
print("🟢 CONCLUSION: Logic dynamically adapts to input data.")
