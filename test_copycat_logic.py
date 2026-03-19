import sys
import os
import pandas as pd
import glob
import numpy as np
from datetime import datetime

# Import the class to test (we'll subclass or mock the config)
# Since the config is global variables in the file, we can't easily override them by import.
# We will copy the logic class here and adjust the threshold for the test.

MIN_WHALE_NOTIONAL = 3_000_000 # TEST THRESHOLD
MIN_WHALE_DTE = 30

def get_dte(exp_date_str):
    try:
        exp = datetime.strptime(exp_date_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        return (exp - today).days
    except: return 0

class WhaleHunterTest:
    def __init__(self):
        self.trade_log = [] 

    def ingest_trade(self, trade):
        if not trade: return None
        sym = trade.get('ticker', '')
        if "SPY" not in sym and "SPX" not in sym: return None
        self.trade_log.append(trade)
        return self.analyze_clusters()

    def analyze_clusters(self):
        if not self.trade_log: return None
        df = pd.DataFrame(self.trade_log)
        
        # Ensure numeric types
        df['strike'] = pd.to_numeric(df['strike'], errors='coerce')
        df['premium'] = pd.to_numeric(df['premium'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
        df['open_interest'] = pd.to_numeric(df['open_interest'], errors='coerce')
        
        alerts = []
        
        for (exp, otype), group in df.groupby(['expiration', 'type']):
            if group.empty: continue
            group = group.sort_values('strike')
            group['strike_diff_pct'] = group['strike'].diff() / group['strike'].shift(1)
            group['cluster_id'] = (group['strike_diff_pct'] > 0.05).cumsum()
            
            clusters = group.groupby('cluster_id').agg({
                'premium': 'sum',
                'volume': 'sum',
                'open_interest': 'sum',
                'strike': ['min', 'max', 'mean'],
                'ticker': 'first'
            })
            
            for cid, row in clusters.iterrows():
                notional = row[('premium', 'sum')]
                vol = row[('volume', 'sum')]
                oi = row[('open_interest', 'sum')]
                avg_strike = row[('strike', 'mean')]
                
                # Check Notional
                if notional < MIN_WHALE_NOTIONAL: continue
                
                # Check DTE
                dte = get_dte(exp)
                if dte <= MIN_WHALE_DTE: continue
                
                # Check Std Dev Distance (Mock Spot)
                spot = 500 # Use a generic spot for test or try to get from data
                # Actually, let's be lenient on StdDev for this test to just see FLOW
                
                # Check Conviction (Vol/OI)
                if oi > 0 and (vol / oi) <= 1.0: continue
                
                alerts.append({
                    "expiration": exp,
                    "option_type": otype,
                    "zone_strike": int(avg_strike),
                    "notional": notional,
                    "volume": vol,
                    "dte": dte
                })
                
        return alerts

def run_test():
    print(f"🚀 Running Copycat Logic Test (Threshold: ${MIN_WHALE_NOTIONAL/1e6:.1f}M)...")
    
    # Load Real Data from Snapshots
    base_path = os.getcwd()
    sweeps_path = os.path.join(base_path, "snapshots_sweeps")
    all_files = sorted(glob.glob(os.path.join(sweeps_path, "*.csv")))
    
    if not all_files:
        print("❌ No snapshot files found in snapshots_sweeps/")
        return

    latest_file = all_files[-1]
    print(f"📂 Loading latest snapshot: {os.path.basename(latest_file)}")
    
    df = pd.read_csv(latest_file)
    print(f"   -> Loaded {len(df)} rows.")
    
    hunter = WhaleHunterTest()
    
    # Convert CSV columns to Hunter format
    # CSV: ticker, parsed_expiry, parsed_strike, parsed_type, total_premium, total_size, open_interest
    count = 0
    for _, row in df.iterrows():
        trade = {
            'ticker': row.get('ticker'),
            'expiration': row.get('parsed_expiry'),
            'strike': row.get('parsed_strike'),
            'type': row.get('parsed_type'), # CALL/PUT -> C/P?
            'premium': row.get('total_premium'),
            'volume': row.get('total_size'),
            'open_interest': row.get('open_interest')
        }
        
        # Normalize Type
        if trade['type'] == 'CALL': trade['type'] = 'C'
        if trade['type'] == 'PUT': trade['type'] = 'P'
        
        hunter.ingest_trade(trade)
        count += 1
        
    print(f"   -> Ingested {count} trades.")
    
    alerts = hunter.analyze_clusters()
    
    if alerts:
        print(f"\n✅ FOUND {len(alerts)} WHALE CLUSTERS > ${MIN_WHALE_NOTIONAL/1e6:.1f}M:")
        for a in alerts:
            print(f"   🐋 {a['expiration']} ${a['zone_strike']}{a['option_type']} | Notional: ${a['notional']/1e6:.1f}M | Vol: {a['volume']} | DTE: {a['dte']}")
    else:
        print(f"\n❌ NO CLUSTERS found > ${MIN_WHALE_NOTIONAL/1e6:.1f}M.")

if __name__ == "__main__":
    run_test()
