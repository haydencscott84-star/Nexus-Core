
import os
import json
import time
from datetime import datetime

FILES = [
    "nexus_portfolio.json",
    "nexus_greeks.json",
    "market_state.json"
]

print("🔍 DATA TRACE STARTED")
print(f"Current System Time: {datetime.now().isoformat()}")

for f in FILES:
    if os.path.exists(f):
        mtime = os.path.getmtime(f)
        age = time.time() - mtime
        size = os.path.getsize(f)
        
        print(f"\n📂 FILE: {f}")
        print(f"   • Age: {age:.1f} seconds ago")
        print(f"   • Size: {size} bytes")
        
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                if f == "nexus_portfolio.json":
                    active = data.get('active_trade', {})
                    print(f"   • Active Trade: {active}")
                    pos_count = len(data.get('positions', []) if 'positions' in data else []) # list or dict?
                    # dashboard structure: "grouped_positions" and "active_trade", but raw positions logic was separate
                    # Wait, dashboard writes "portfolio_snapshot" which has "active_trade" and "grouped_positions".
                    # It doesn't seem to dump raw positions list into the root, but inside account_metrics? No.
                    # Let's see what keys are there.
                    print(f"   • Keys: {list(data.keys())}")
                    
                elif f == "nexus_greeks.json":
                    trade = data.get('active_trade', {})
                    greeks = data.get('greeks', {})
                    print(f"   • Trade Ticker: {trade.get('ticker')}")
                    print(f"   • Greeks Time: {data.get('timestamp')}")
                    
                elif f == "market_state.json":
                    # Auditor reads this too.
                    print(f"   • Keys: {list(data.keys())}")
                    
        except Exception as e:
            print(f"   ❌ Read Error: {e}")
    else:
        print(f"\n❌ MISSING FILE: {f}")

print("\n🏁 TRACE COMPLETE")
