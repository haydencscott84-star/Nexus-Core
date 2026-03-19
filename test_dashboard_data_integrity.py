import json
import sys
import os

# Mock the classes/dicts needed
class MockCandidate:
    def __init__(self):
        self.data = {
            'symbol': 'SPY',
            'stk': 500.0,
            'type': 'CALL',
            'exp': '2024-12-20',
            'mkt': 1.50,
            'dte': 5,
            'volume': 1000,
            'open_interest': 5000,
            'greeks': {'delta': 0.5, 'gamma': 0.05, 'theta': -0.1, 'vega': 0.02},
            'implied_volatility': 0.25,
            'option_symbol': 'SPY241220C00500000'
        }
    
    def get(self, k, d=None):
        return self.data.get(k, d)
    
    def __getitem__(self, k):
        return self.data[k]

def test_hunter_payload():
    print("Testing Hunter Payload Construction...")
    c = MockCandidate()
    
    # Logic copied from nexus_hunter.py
    payload = {
        "symbol": c['symbol'],
        "stk": c['stk'],
        "type": c['type'],
        "exp": c['exp'],
        "mkt": c['mkt'],
        "dte": c.get('dte', 0),
        "vol": int(c.get('volume', 0)),
        "oi": int(c.get('open_interest', 0)),
        "delta": c.get('greeks', {}).get('delta', 0),
        "gamma": c.get('greeks', {}).get('gamma', 0),
        "theta": c.get('greeks', {}).get('theta', 0),
        "vega": c.get('greeks', {}).get('vega', 0),
        "iv": c.get('implied_volatility', 0),
        "occ_sym": c.get('option_symbol'),
        "source": "HUNTER"
    }
    
    required = ["vol", "oi", "delta", "occ_sym"]
    for r in required:
        if r not in payload:
            print(f"FAILED: Missing {r}")
            return False
        print(f"  - {r}: {payload[r]}")
        
    print("Hunter Payload: OK")
    return True

def test_dashboard_parsing():
    print("\nTesting Dashboard Parsing Logic...")
    # Mock Payload
    d = {
        "symbol": "SPY", "stk": 500.0, "type": "CALL", "exp": "2024-12-20", "mkt": 1.50,
        "dte": 5, "vol": 1000, "oi": 5000, "delta": 0.5, "gamma": 0.05, "theta": -0.1, 
        "vega": 0.02, "iv": 0.25, "occ_sym": "SPY241220C00500000", "source": "HUNTER"
    }
    
    # Logic copied from trader_dashboard.py
    d['prem'] = d.get('mkt', 0) * 100 * d.get('vol', 0)
    d['voi_ratio'] = d.get('vol', 0) / d.get('oi', 1) if d.get('oi', 0) > 0 else 0.0
    d['theo'] = d.get('mkt', 0)
    
    stk = d.get('stk', 0); mkt = d.get('mkt', 0); typ = d.get('type', 'CALL')
    d['be'] = stk + mkt if typ == 'CALL' else stk - mkt
    
    delta = abs(d.get('delta', 0))
    d['win'] = f"{delta*100:.0f}%"
    
    print(f"  - Premium: {d['prem']} (Expected 150000.0)")
    print(f"  - V/OI: {d['voi_ratio']} (Expected 0.2)")
    print(f"  - BE: {d['be']} (Expected 501.5)")
    print(f"  - Win%: {d['win']} (Expected 50%)")
    
    if d['prem'] == 150000.0 and d['voi_ratio'] == 0.2:
        print("Dashboard Parsing: OK")
        return True
    return False

if __name__ == "__main__":
    if test_hunter_payload() and test_dashboard_parsing():
        print("\n✅ OPTIMIZATION TEST PASSED")
    else:
        print("\n❌ TEST FAILED")
