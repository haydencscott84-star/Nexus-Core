import sys
import asyncio
from unittest.mock import MagicMock
import pandas as pd
import datetime

# 1. Define Concrete Base Class for App
class MockApp:
    def __init__(self): pass
    def query_one(self, *args): 
        m = MagicMock()
        m.update = MagicMock()
        return m
    def run_worker(self, *args, **kwargs): pass
    def set_interval(self, *args): pass
    def compose(self): pass

# 2. Mock Textual Modules
mock_textual_app = MagicMock()
mock_textual_app.App = MockApp
sys.modules['textual.app'] = mock_textual_app
sys.modules['textual.widgets'] = MagicMock()
sys.modules['textual.containers'] = MagicMock()
sys.modules['rich.text'] = MagicMock()

# 3. Import Target
import mtf_nexus

# 4. Mock TradeStationManager with Dummy Data
class MockTSManager:
    def __init__(self, *args): pass
    def get_historical_data(self, ticker, unit, interval, bars_back):
        rows = []
        base_price = 400.0
        
        is_daily = (unit == "Daily")
        delta = datetime.timedelta(days=1) if is_daily else datetime.timedelta(hours=1)
        
        # Make enough data
        count = 500
        start_time = datetime.datetime.now().replace(microsecond=0, second=0, minute=0)
        
        for i in range(count):
            t = start_time - (delta * (count - i))
            val = base_price + (i * 2.0) # Steep Uptrend
            rows.append({
                "TimeStamp": t.isoformat(),
                "Close": val, 
                "High": val + 1, "Low": val - 1, "Open": val
            })
        return rows

mtf_nexus.TradeStationManager = MockTSManager

# 5. Patch App
mtf_nexus.MTFNexusApp.log_msg = lambda self, m: print(f"LOG: {m}")
mtf_nexus.MTFNexusApp.check_and_alert = lambda self, k, m, c: print(f"CAPTURED ALERT: {k}\nCONTENT:\n{m}")

# 6. Run Test
async def run_test():
    print("Initializing App...")
    app = mtf_nexus.MTFNexusApp()
    app.is_startup = True # Force Logic to bypass throttle
    
    print("Running Analysis...")
    await app.async_analysis()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    loop.run_until_complete(run_test())
