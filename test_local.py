import datetime

try:
    ts_raw = "2026-01-02T19:04:25Z"
    t_obj = datetime.datetime.fromisoformat(ts_raw.replace('Z', '+00:00'))
    now_obj = datetime.datetime.now(t_obj.tzinfo)
    diff = now_obj - t_obj
    days = diff.days; hours = diff.seconds // 3600; mins = (diff.seconds % 3600) // 60
    if days > 0: age_str = f"{days}d {hours}h"
    elif hours > 0: age_str = f"{hours}h {mins}m"
    else: age_str = f"{mins}m"
    print(f"AGE: {age_str}")
except Exception as e:
    print(f"AGE ERROR: {e}")

try:
    exp_raw = "2026-01-30T00:00:00Z"
    d_obj = datetime.datetime.fromisoformat(exp_raw.replace('Z', '+00:00'))
    exp_str = d_obj.strftime('%Y-%m-%d')
    print(f"EXP: {exp_str}")
except Exception as e:
    print(f"EXP ERROR: {e}")
