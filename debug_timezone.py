
import datetime
import os
try:
    import pytz
    has_pytz = True
except ImportError:
    has_pytz = False

def check_time():
    print(f"Has pytz: {has_pytz}")
    
    # Method 1: Pytz
    if has_pytz:
        try:
            tz = pytz.timezone('US/Eastern')
            now_tz = datetime.datetime.now(tz)
            print(f"Pytz 'US/Eastern': {now_tz} (Hour: {now_tz.hour})")
        except Exception as e:
            print(f"Pytz Error: {e}")

    # Method 2: Manual Offset
    now_utc = datetime.datetime.utcnow()
    now_manual = now_utc - datetime.timedelta(hours=5)
    print(f"UTC: {now_utc}")
    print(f"Manual UTC-5: {now_manual} (Hour: {now_manual.hour})")
    
    # Logic Test
    is_open_pytz = False
    if has_pytz:
        try:
            now = datetime.datetime.now(pytz.timezone('US/Eastern'))
            is_open_pytz = (7 <= now.hour < 17)
        except: pass
        
    is_open_manual = (7 <= now_manual.hour < 17)
    
    print(f"Window Open (Pytz)? {is_open_pytz}")
    print(f"Window Open (Manual)? {is_open_manual}")

if __name__ == "__main__":
    check_time()
