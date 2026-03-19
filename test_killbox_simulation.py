
import pandas as pd
import numpy as np
import sys
import os

# Ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# MOCK CONSTANTS
SPY_PRICE = 685.69 # Stale Price from Screenshot
SPX_PRICE = 6816.10

def simulate_kill_box():
    print(f"🚀 Simulating Kill Box with SPY=${SPY_PRICE}, SPX=${SPX_PRICE}")
    
    # 1. Create Dummy Data (Mixed SPY/SPX)
    data = []
    # SPY Calls (Strike 600 - Deep ITM if price 685) -> Breakeven ~605. Price (685) > 605 -> PROFIT (Not Trap)
    data.append({'ticker': 'SPY', 'strike': 600.0, 'expiry': '2025-12-19', 'type': 'CALL', 'premium': 85.0, 'vol': 100, 'oi': 5000, 'delta': 0.90})
    # SPY Puts (Strike 600 - OTM) -> Breakeven ~595. Price (685) > 595 -> TRAPPED BEARS (Trap)
    data.append({'ticker': 'SPY', 'strike': 600.0, 'expiry': '2025-12-19', 'type': 'PUT', 'premium': 0.50, 'vol': 1000, 'oi': 10000, 'delta': -0.05})
    
    # SPX Rows
    data.append({'ticker': 'SPX', 'strike': 6000.0, 'expiry': '2025-12-19', 'type': 'PUT', 'premium': 5.0, 'vol': 500, 'oi': 2000, 'delta': -0.10})
    
    active_df = pd.DataFrame(data)
    active_df['dte'] = 15.0 # Mock DTE
    print(f"📊 Input Data:\n{active_df}")

    # --- LOGIC REPLICATION FROM analyze_snapshots.py ---
    
    # 1. Calls
    calls = active_df[active_df['type'] == 'CALL'].copy()
    calls['oi_delta'] = calls['oi'] * calls['delta'] * 100.0
    calls['avg_prem'] = calls['premium'] / calls['vol']
    calls['breakeven'] = calls['strike'] + (calls['avg_prem'] / 100.0)
    calls['status'] = calls.apply(lambda x: "TRAPPED BULLS" if (SPY_PRICE if x['ticker']=='SPY' else SPX_PRICE) < x['breakeven'] else "PROFIT", axis=1)
    
    # 2. Puts
    puts = active_df[active_df['type'] == 'PUT'].copy()
    puts['oi_delta'] = puts['oi'] * puts['delta'] * 100.0
    puts['avg_prem'] = puts['premium'] / puts['vol']
    puts['breakeven'] = puts['strike'] - (puts['avg_prem'] / 100.0)
    puts['status'] = puts.apply(lambda x: "TRAPPED BEARS" if (SPY_PRICE if x['ticker']=='SPY' else SPX_PRICE) > x['breakeven'] else "PROFIT", axis=1)

    print("\n🧐 Call Status Check:")
    print(calls[['ticker', 'strike', 'breakeven', 'status']])
    print("\n🧐 Put Status Check:")
    print(puts[['ticker', 'strike', 'breakeven', 'status']])

    # 3. Merge & Filter
    merged = pd.concat([calls, puts], ignore_index=True)
    trapped = merged[merged['status'].str.contains("TRAPPED")].copy()
    
    print(f"\n🕸️ Trapped Rows: {len(trapped)}")
    print(trapped)

    # 4. Split
    spy_traps = trapped[trapped['ticker'] == 'SPY'].copy()
    print(f"\n🕵️ SPY Traps (Before Enrichment): {len(spy_traps)}")
    
    if spy_traps.empty:
        print("❌ CRITICAL: No SPY Traps found! Logic is filtering them out.")
    else:
        print("✅ SPY Traps exist. Proceeding to Enrichment...")
        # Simulate Lazy Import
        try:
             # Just use identity for test
             enrich_traps_with_greeks = lambda x: x
             spy_traps = enrich_traps_with_greeks(spy_traps)
             print("✅ Enrichment Passed (Mock).")
        except Exception as e:
            print(f"❌ Enrichment Failed: {e}")

if __name__ == "__main__":
    simulate_kill_box()
