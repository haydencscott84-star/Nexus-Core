
import datetime
import pytz
from datetime import timedelta

# Mocking the functions from spx_profiler_nexus.py

ET = pytz.timezone('US/Eastern')

def get_now_et(): 
    try: return datetime.datetime.now(ET)
    except: return datetime.datetime.utcnow() - timedelta(hours=5)

def get_trading_date(ref_date=None):
    if ref_date is None: ref_date = get_now_et().date()
    while ref_date.weekday() >= 5: ref_date -= timedelta(days=1)
    return ref_date

# Simulation
today = get_trading_date()
print(f"System Trading Date: {today}")

# Sample Timestamps from UW API (Hypothetical)
samples = [
    "2026-01-17T15:00:00.000Z", # Today (Saturday)
    "2026-01-16T15:00:00.000Z", # Yesterday (Friday)
    "2026-01-16T20:00:00.000Z", # Friday After Close
    "2026-01-17T00:00:00.000Z", # Saturday Early
]

print("-" * 30)
for ts_str in samples:
    try:
        t_date_str = ts_str.split('T')[0]
        today_str = today.isoformat()
        
        match = (t_date_str == today_str)
        print(f"Trade TS: {ts_str} -> Date: {t_date_str} | System: {today_str} | Match: {match}")
    except Exception as e:
        print(f"Error parsing {ts_str}: {e}")
