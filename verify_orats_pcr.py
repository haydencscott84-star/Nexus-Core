
import requests
import os
import json
import datetime
from collections import defaultdict

ORATS_API_KEY = os.getenv('ORATS_API_KEY', os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY"))
TICKER = "SPY"

def calculate_pc_ratios_and_vol(orats_data):
    exp_data = {} 
    
    # Debug: Check first row keys
    if len(orats_data) > 0:
        print(f"Sample Row: {list(orats_data[0].keys())}")
        
    for r in orats_data:
        try:
            exp = r.get('expirDate')
            if not exp: continue
            
            if exp not in exp_data:
                exp_data[exp] = {'puts_oi': 0, 'calls_oi': 0, 'puts_vol': 0, 'calls_vol': 0}
            
            # Logic from spy_profiler_nexus_v2.py
            if 'putOpenInterest' in r and 'callOpenInterest' in r:
                exp_data[exp]['puts_oi'] += int(r.get('putOpenInterest', 0))
                exp_data[exp]['calls_oi'] += int(r.get('callOpenInterest', 0))
                exp_data[exp]['puts_vol'] += int(r.get('putVolume', 0))
                exp_data[exp]['calls_vol'] += int(r.get('callVolume', 0))
            elif r.get('optionType') == 'P':
                exp_data[exp]['puts_oi'] += int(r.get('openInterest', 0))
                exp_data[exp]['puts_vol'] += int(r.get('volume', 0))
            elif r.get('optionType') == 'C':
                exp_data[exp]['calls_oi'] += int(r.get('openInterest', 0))
                exp_data[exp]['calls_vol'] += int(r.get('volume', 0))
        except: continue
            
    pc_oi_map = {}
    pc_vol_map = {}
    for exp, data in exp_data.items():
        pc_oi_map[exp] = data['puts_oi'] / data['calls_oi'] if data['calls_oi'] > 0 else 0.0
        pc_vol_map[exp] = data['puts_vol'] / data['calls_vol'] if data['calls_vol'] > 0 else 0.0
        
    return pc_oi_map, pc_vol_map, exp_data

print(f"Fetching ORATS data for {TICKER}...")
try:
    url = "https://api.orats.io/datav2/live/strikes"
    params = {'token': ORATS_API_KEY, 'ticker': TICKER}
    r = requests.get(url, params=params, timeout=15)
    data = r.json().get('data', [])
    print(f"Items fetched: {len(data)}")
    
    pc_oi, pc_vol, raw = calculate_pc_ratios_and_vol(data)
    
    print("\n--- RESULTS BY EXPIRY ---")
    sorted_exps = sorted(pc_oi.keys())
    for exp in sorted_exps[:5]: # Show first 5
        print(f"Exp: {exp} | P/C Vol: {pc_vol[exp]:.2f} | P/C OI: {pc_oi[exp]:.2f} (Vol: {raw[exp]['puts_vol']}/{raw[exp]['calls_vol']})")
        
except Exception as e:
    print(f"Error: {e}")
