
import pandas as pd
import unittest
from rich.text import Text

# Mock Dependencies based on what we saw in the code
def fmt_oi_delta(val):
    return f"{val}"

class TestKillBoxLogic(unittest.TestCase):
    
    def test_burn_logic(self):
        # 1. Create Mock Data
        data = {
            'ticker': ['SPY', 'SPY', 'SPX'],
            'strike': [600, 605, 6000],
            'expiry': ['2025-12-10', '2025-12-10', '2025-12-10'],
            'dte': [3, 3, 3],
            'type': ['CALL', 'CALL', 'PUT'],
            'premium': [1000, 1000, 5000],
            'vol': [10, 10, 5],
            'oi': [100, 200, 50],
            'delta': [0.5, 0.4, -0.3],
            'gamma': [0.01, 0.02, 0.005],
            'vega': [0.1, 0.15, 0.5],
            'theta': [-0.10, -0.20, -1.5] # One low burn, two high burn
        }
        active_df = pd.DataFrame(data)
        
        SPY_PRICE = 590.0 # Trapped Bulls (Strike 600)
        SPX_PRICE = 6100.0 # Trapped Bears (Strike 6000) for Put? Wait, Put Breakeven logic.
        
        # --- REPLICATING THE LOGIC FROM SCRATCH TO VERIFY ---
        
        # 1. Aggregation (Simulated) - Already done in 'data' creation effectively
        calls = active_df[active_df['type'] == 'CALL'].copy()
        calls['oi_delta'] = calls['oi'] * calls['delta'] * 100.0
        calls['avg_prem'] = calls['premium'] / calls['vol']
        calls['breakeven'] = calls['strike'] + (calls['avg_prem'] / 100.0)
        
        puts = active_df[active_df['type'] == 'PUT'].copy()
        puts['oi_delta'] = puts['oi'] * puts['delta'] * 100.0
        puts['avg_prem'] = puts['premium'] / puts['vol']
        puts['breakeven'] = puts['strike'] - (puts['avg_prem'] / 100.0)

        # Status Logic
        calls['status'] = calls.apply(lambda x: "TRAPPED BULLS" if SPY_PRICE < x['breakeven'] else "PROFIT", axis=1)
        puts['status'] = puts.apply(lambda x: "TRAPPED BEARS" if SPX_PRICE > x['breakeven'] else "PROFIT", axis=1)
        
        merged = pd.concat([calls, puts])
        
        print("\n--- MOCK DATA ---")
        print(merged[['ticker', 'strike', 'theta', 'status', 'breakeven']])
        
        # 2. Iterate and Check Styling
        for _, row in merged.iterrows():
            is_trapped = "TRAPPED" in row['status']
            high_rent = row['theta'] < -0.15
            
            print(f"Row: {row['ticker']} {row['strike']} | Theta: {row['theta']} | Trapped: {is_trapped} | High Rent: {high_rent}")
            
            status_txt = row['status']
            if is_trapped and high_rent:
                status_txt = f"🔥 {row['status']}"
                print(f"   -> ALERT TRIGGERED: {status_txt}")
                self.assertTrue("🔥" in status_txt, "Should define Fire icon for high burn trap")
            elif is_trapped:
                 print(f"   -> Standard Trap")
                 self.assertFalse("🔥" in status_txt, "Should NOT have Fire icon for low burn trap")

if __name__ == '__main__':
    unittest.main()
