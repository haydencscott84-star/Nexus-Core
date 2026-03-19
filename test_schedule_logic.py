import datetime
import pytz

# Mocking the logic to be implemented
class Scheduler:
    def __init__(self):
        self.last_run_time = None
        self.tz = pytz.timezone('US/Eastern')

    def get_interval(self, mock_now=None):
        if mock_now:
            now = mock_now.replace(tzinfo=self.tz)
        else:
            now = datetime.datetime.now(self.tz)
            
        # Market Hours: Mon-Fri, 9:30 - 16:00
        is_weekday = now.weekday() < 5 # 0-4 is Mon-Fri
        
        # Create time objects for comparison
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        is_market_hours = is_weekday and (market_open <= now <= market_close)
        
        if is_market_hours:
            return 900, "MARKET_HOURS (15m)"
        else:
            return 14400, "OFF_HOURS (4h)"

def test_logic():
    s = Scheduler()
    
    # Test Cases
    scenarios = [
        ("Monday 10:00 AM (Market Open)", datetime.datetime(2025, 12, 1, 10, 0)),
        ("Monday 9:00 AM (Pre-Market)", datetime.datetime(2025, 12, 1, 9, 0)),
        ("Monday 4:01 PM (After-Hours)", datetime.datetime(2025, 12, 1, 16, 1)),
        ("Saturday 12:00 PM (Weekend)", datetime.datetime(2025, 12, 6, 12, 0)),
        ("Sunday 11:00 PM (Weekend)", datetime.datetime(2025, 12, 7, 23, 0)),
    ]
    
    print("🧪 TESTING SCHEDULER LOGIC (NY TIME)...")
    for name, dt in scenarios:
        interval, label = s.get_interval(dt)
        print(f"Scenario: {name}")
        print(f"   -> Time: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   -> Result: {label} ({interval}s)")
        
        # Assertions
        if "Market Open" in name and interval != 900: print("❌ FAIL")
        elif "Pre-Market" in name and interval != 14400: print("❌ FAIL")
        elif "After-Hours" in name and interval != 14400: print("❌ FAIL")
        elif "Weekend" in name and interval != 14400: print("❌ FAIL")
        else: print("✅ PASS")
        print("-" * 30)

if __name__ == "__main__":
    test_logic()
