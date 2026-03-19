import datetime
import zoneinfo

try: import pytz; print(f"Pytz: Yes. US/Eastern: {datetime.datetime.now(pytz.timezone('US/Eastern'))}")
except: print("Pytz: No")

now_utc = datetime.datetime.utcnow()
print(f"UTC: {now_utc}")
tz = zoneinfo.ZoneInfo("America/New_York")
now_et_manual = datetime.datetime.now(tz).replace(tzinfo=None)
print(f"Zoneinfo ET: {now_et_manual}")
print(f"Hour: {now_et_manual.hour}")
print(f"Is Open (7-17): {7 <= now_et_manual.hour < 17}")
