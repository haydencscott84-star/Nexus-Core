
import datetime, pytz
ET = pytz.timezone('US/Eastern')

def get_ny_time(): return datetime.datetime.now(ET)
def get_trading_date(): 
    d = get_ny_time().date()
    # Logic from script
    from datetime import timedelta
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d

print(f"Server Time UTC: {datetime.datetime.utcnow()}")
print(f"NY Time: {get_ny_time()}")
print(f"Trading Date: {get_trading_date()}")
