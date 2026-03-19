
import datetime, pytz
ET = pytz.timezone('US/Eastern')
UTC = pytz.utc

def get_ny_time(): return datetime.datetime.now(ET)
def get_trading_date(): 
    d = get_ny_time().date()
    while d.weekday() >= 5: d -= datetime.timedelta(days=1)
    return d

def is_from_today(ts):
    if not ts: return False
    try:
        if isinstance(ts, (int, float)): d = datetime.datetime.fromtimestamp(ts, tz=UTC).astimezone(ET).date()
        elif isinstance(ts, str): d = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(ET).date()
        else: return False
        return d == get_trading_date()
    except: return False

print(f"System Time: {datetime.datetime.now()}")
print(f"NY Time: {get_ny_time()}")
print(f"Trading Date: {get_trading_date()}")

ts = 1769704842.177
dt = datetime.datetime.fromtimestamp(ts, tz=UTC).astimezone(ET)
print(f"TS {ts} -> {dt} -> Date: {dt.date()}")
print(f"Is Today? {is_from_today(ts)}")
