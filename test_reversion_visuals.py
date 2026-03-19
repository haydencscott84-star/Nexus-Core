
import asyncio
import pandas as pd
import numpy as np
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta

# Mock the imports
sys.modules['tradestation_explorer'] = MagicMock()
sys.modules['nexus_config'] = MagicMock()
sys.modules['nexus_config'].TS_CLIENT_ID = "mock_id"
sys.modules['nexus_config'].TS_CLIENT_SECRET = "mock_secret"
sys.modules['nexus_config'].TS_ACCOUNT_ID = "mock_account"

# Mock Textual App functionality locally since we are headless
# We need to ensure backtest_reversion_hourly can be imported even if Textual is present but we want to intercept the UI calls.
# The script imports textual... assuming it's installed.

import backtest_reversion_hourly

# Mock Data Generator
def generate_mock_candles(n_candles, timeframe='hourly'):
    data = []
    price = 600.0
    start_time = datetime.now() - timedelta(hours=n_candles)
    
    for i in range(n_candles):
        change = np.random.normal(0, 5.0) # Increased volatility for guaranteed signals
        price += change
        ts_val = start_time + timedelta(hours=i) if timeframe == 'hourly' else start_time + timedelta(days=i)
        data.append({
            'TimeStamp': ts_val.isoformat(),
            'Close': price, 'Open': price, 'High': price + 0.5, 'Low': price - 0.5, 'Volume': 1000
        })
    return data

class TestReversionCrashProof(unittest.TestCase):
    
    def test_hourly_threading_crash_fix(self):
        print("\n=== PROVING HOURLY THREADING FIX ===")
        app = backtest_reversion_hourly.ReversionHourlyApp()
        
        # 1. Mock the API to return data successfully
        mock_ts = MagicMock()
        mock_data = generate_mock_candles(2000, 'hourly')
        mock_ts.get_historical_data.return_value = mock_data
        mock_ts.get_quote_snapshot.return_value = {'Last': 605.0} # Sync return!
        
        # 2. Mock UI components so update_ui doesn't fail on query_one
        mock_table_up = MagicMock()
        mock_table_down = MagicMock()
        
        # Side effect to print what gets added to the table
        def print_row(*args, **kwargs):
            # args contains the Renderables (Text objects)
            # We explicitly convert them to string to show what would be displayed
            row_text = " | ".join([str(arg).replace('\\n', '') for arg in args]) 
            print(f"   [TABLE ROW ADDED]: {row_text}")

        mock_table_up.add_row.side_effect = print_row
        mock_table_down.add_row.side_effect = print_row
        
        def get_table(*args):
            css_id = args[0]
            if css_id == "#table_upside": return mock_table_up
            if css_id == "#table_downside": return mock_table_down
            
            # Mock the status label too!
            if css_id == "#status_lbl":
                m = MagicMock()
                m.update.side_effect = lambda msg: print(f"   [STATUS UPDATE]: {msg}")
                return m
                
            return MagicMock()

        app.query_one = MagicMock(side_effect=get_table)
        app.notify = MagicMock()
        
        # 3. CRITICAL: Mock call_from_thread to FAIL if called
        # If the code still uses call_from_thread, this Mock will record a call, 
        # or we can make it raise an error to simulate what Textual does on MainThread.
        app.call_from_thread = MagicMock(side_effect=Exception("CRASH! call_from_thread was called!"))
        
        # Patch TradeStationManager class to return our mock
        with patch('backtest_reversion_hourly.TradeStationManager', return_value=mock_ts):
            
            # 4. RUN logic synchronously (simulating the async callback on main thread)
            # using asyncio.run logic style or just direct await execution
            
            async def run_test():
                print("Running async_analysis()...")
                await app.async_analysis()
                print("async_analysis() completed.")
            
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(run_test())
                print("✅ PASSED: async_analysis ran without invoking call_from_thread.")
            except Exception as e:
                print(f"❌ FAILED: {e}")
                self.fail(f"Test failed with error: {e}")
            finally:
                loop.close()

if __name__ == '__main__':
    unittest.main()
