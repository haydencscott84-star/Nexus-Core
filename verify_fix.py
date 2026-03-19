
import sys
import os
import pandas as pd
from datetime import datetime, timedelta
from rich.text import Text

# Add script dir to path
sys.path.append(os.getcwd())

try:
    from analyze_snapshots import StrategicHUD
    print("✅ Import successful")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    sys.exit(1)

# Mock Data
def create_mock_df():
    data = []
    for ticker in ['SPY', 'SPX']:
        data.append({
            'ticker': ticker,
            'strike': 5000 if ticker=='SPX' else 500,
            'expiry': (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d'),
            'date': datetime.now().date(),
            'type': 'CALL',
            'premium': 1000,
            'vol': 100,
            'oi': 500,
            'delta': 0.5,
            'gamma': 0.05,
            'vega': 0.1,
            'theta': -0.1,
            'underlying_price': 500.0 if ticker=='SPY' else 5000.0,
            'is_bull': True,
            'dte': 30
        })
    
    df = pd.DataFrame(data)
    df['expiry_dt'] = pd.to_datetime(df['expiry'])
    return df

class MockTable:
    def __init__(self):
        self.rows = []
        self.columns = []
        self.cursor_type = None

    def clear(self, columns=False): 
        self.rows = []
        if columns: self.columns = []

    def add_columns(self, *args, **kwargs):
        self.columns.extend(args)

    def add_row(self, *args, **kwargs):
        self.rows.append(args)

def run_test():
    print("🚀 Starting Logic Verification...")
    
    app = StrategicHUD()
    app.current_df = create_mock_df()
    app.last_spot_price = 500.0
    
    # Mock query_one
    mock_spx = MockTable()
    mock_spy = MockTable()
    
    def query_one(selector, type=None):
        if "spx" in selector: return mock_spx
        if "spy" in selector: return mock_spy
        return MockTable()
        
    app.query_one = query_one
    app.log_msg = lambda x: print(f"LOG: {x}")
    
    print("   -> Testing build_kill_box...")
    try:
        app.build_kill_box()
        print("      ✅ build_kill_box passed")
        
        # Verify Headers (Manually checking if columns match expectation would require more mocking, assumes run passed)
        print(f"      Rows in SPX Table: {len(mock_spx.rows)}")
        print(f"      Rows in SPY Table: {len(mock_spy.rows)}")
        
        if len(mock_spx.rows) > 0 and len(mock_spx.rows[0]) >= 10:
             print("      ✅ SPX Table has correct column count (>=10 for Greeks)")
        else:
             print(f"      ⚠️ SPX Table seems short on columns: {len(mock_spx.rows[0]) if mock_spx.rows else 0}")

    except Exception as e:
        print(f"      ❌ build_kill_box CRASHED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
        
    print("\n✅ VERIFICATION COMPLETE")

if __name__ == "__main__":
    run_test()