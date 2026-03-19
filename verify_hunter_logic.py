import requests
import os
import json
from datetime import datetime

# --- CONFIG ---
UW_API_KEY = os.getenv('UNUSUAL_WHALES_API_KEY', os.environ.get("UNUSUAL_WHALES_API_KEY", "YOUR_UW_API_KEY"))
ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))

# --- LENIENCY PROTOCOL (Copied from nexus_hunter.py) ---
class LeniencyEngine:
    def __init__(self, min_delta=0.30):
        self.min_delta = min_delta

    def score(self, c):
        score = 100.0
        
        # 1. Delta Threshold (Range Filter)
        d = abs(c.get('greeks', {}).get('delta') or 0.0)
        
        if d < self.min_delta:
            # Below minimum delta -> Heavy Penalty
            score -= (self.min_delta - d) * 500 # 0.01 miss = -5 pts
            if d < (self.min_delta - 0.10): score = 0 # Kill if way off
        else:
            # Above minimum -> No Penalty (Valid Range)
            pass
        
        # 2. Spread Penalty (Liquidity)
        bid = float(c.get('bid') or 0); ask = float(c.get('ask') or 0)
        if ask > 0:
            spread = (ask - bid) / ask
            if spread > 0.10: score -= 50 # Kill score if spread > 10%
            elif spread > 0.05: score -= 20
            
        # 3. Edge Bonus (Value) - PRIMARY DRIVER
        edge = c.get('edge', 0)
        # Boost weight: 5% edge was +10, now make it +25 (5x multiplier)
        score += edge * 5 
        
        return max(0, round(score, 1))

def verify_logic():
    print("--- VERIFYING HUNTER LOGIC (SYNC) ---")
    
    target_delta = 0.30
    min_dte = 7
    max_dte = 45
    target_type = "CALL"
    
    print(f"Parameters: {target_type} | Delta: {target_delta} | DTE: {min_dte}-{max_dte}")

    # 1. FETCH UW
    print("\n[1] Fetching Unusual Whales Data...")
    url = f"https://api.unusualwhales.com/api/screener/option-contracts"
    params = {'ticker_symbol': 'SPY', 'min_volume': 100, 'min_dte': min_dte, 'max_dte': max_dte}
    headers = {'Authorization': f'Bearer {UW_API_KEY}'}
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"❌ UW API Error: {r.status_code}")
            return
        uw_data = r.json().get('data', [])
        print(f"✅ UW Data Fetched: {len(uw_data)} contracts.")
    except Exception as e:
        print(f"❌ UW Exception: {e}")
        return

    # 2. FETCH ORATS
    print("\n[2] Fetching ORATS Data...")
    o_url = "https://api.orats.io/datav2/live/strikes"
    try:
        r = requests.get(o_url, params={'token': ORATS_API_KEY, 'ticker': 'SPY'}, timeout=10)
        if r.status_code != 200:
            print(f"❌ ORATS API Error: {r.status_code}")
            return
        orats_data = r.json().get('data', [])
        print(f"✅ ORATS Data Fetched: {len(orats_data)} strikes.")
    except Exception as e:
        print(f"❌ ORATS Exception: {e}")
        return

    # 3. MAP ORATS (Testing the Fix)
    print("\n[3] Mapping ORATS Data...")
    theo_map = {}
    try:
        for o in orats_data:
            exp = o['expirDate']
            stk = float(o['strike'])
            
            # CALL
            key_c = f"{exp}|{stk:.1f}|C"
            theo_map[key_c] = float(o.get('callValue') or 0)
            
            # PUT
            key_p = f"{exp}|{stk:.1f}|P"
            theo_map[key_p] = float(o.get('putValue') or 0)
        print(f"✅ ORATS Mapped Successfully. Map size: {len(theo_map)}")
    except Exception as e:
        print(f"❌ ORATS Mapping Failed: {e}")
        return

    # 4. PROCESS & SCORE (Testing UW Parsing Fix)
    print("\n[4] Processing & Scoring...")
    engine = LeniencyEngine(target_delta)
    results = []
    
    try:
        for c in uw_data:
            # PARSE OPTION SYMBOL
            sym = c.get('option_symbol', '')
            if len(sym) < 15: continue
            
            suffix = sym[-15:]
            date_str = suffix[:6]
            type_char = suffix[6]
            strike_str = suffix[7:]
            
            exp = f"20{date_str[:2]}-{date_str[2:4]}-{date_str[4:]}"
            stk = float(strike_str) / 1000.0
            c_type = 'CALL' if type_char == 'C' else 'PUT'
            
            if c_type != target_type: continue

            o_type_code = 'C' if c_type == 'CALL' else 'P'
            key = f"{exp}|{stk:.1f}|{o_type_code}"
            
            theo = theo_map.get(key, 0)
            mkt = float(c.get('close') or 0)
            
            edge = 0
            if theo > 0 and mkt > 0:
                edge = ((theo - mkt) / theo) * 100
            
            c['greeks'] = {
                'delta': float(c.get('delta') or 0),
                'gamma': float(c.get('gamma') or 0),
                'theta': float(c.get('theta') or 0),
                'vega': float(c.get('vega') or 0)
            }
            c['exp'] = exp
            c['stk'] = stk
            c['type'] = c_type
            c['edge'] = edge
            
            score = engine.score(c)
            if score > 50:
                results.append((score, c, mkt, theo, edge))
        
        print(f"✅ Processing Complete. Found {len(results)} matches.")
        
        # Print Top 3
        results.sort(key=lambda x: x[0], reverse=True)
        print("\n--- TOP 3 RESULTS ---")
        for score, c, mkt, theo, edge in results[:3]:
            # Recalculate display metrics for verification
            try:
                d_obj = datetime.strptime(c['exp'], "%Y-%m-%d")
                dte = (d_obj - datetime.now()).days
            except: dte = 0
            be = c['stk'] + mkt if c['type'] == 'CALL' else c['stk'] - mkt
            
            print(f"Score: {score} | {c['ticker_symbol']} {c['exp']} (DTE:{dte}) {c['stk']} {c['type']} | Mkt: {mkt:.2f} Theo: {theo:.2f} Edge: {edge:.1f}% BE: {be:.2f}")
            
    except Exception as e:
        print(f"❌ Processing Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_logic()
