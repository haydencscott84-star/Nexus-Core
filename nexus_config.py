import os
# NEXUS CONFIGURATION FILE
# Shared credentials and settings for the Nexus Trading Suite
import datetime
try: import pytz
except: pytz = None

# --- TRADESTATION CREDENTIALS ---
TS_CLIENT_ID = os.environ.get("TS_CLIENT_ID", "YOUR_TS_CLIENT_ID")
TS_CLIENT_SECRET = os.environ.get("TS_CLIENT_SECRET", "YOUR_TS_CLIENT_SECRET")
TS_ACCOUNT_ID = os.environ.get("TS_ACCOUNT_ID", "YOUR_ACCOUNT_ID")
LIVE_TRADING = True # Set to False for SIM environment

# Discord Webhook
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")
# Health Center Webhook
HEALTH_DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")
SNIPER_STATUS_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")

# --- ZMQ PORTS ---
ZMQ_PORT_MARKET = 5555
ZMQ_PORT_ACCOUNT = 5566
ZMQ_PORT_EXEC = 5567
ZMQ_PORT_CONTROL = 5568
ZMQ_PORT_CONTROL = 5568
ZMQ_PORT_OPTION_TICK = 5569
ZMQ_PORT_BAR = 5570
ZMQ_PORT_LOGS = 5572
ZMQ_PORT_NOTIFICATIONS = 5575

# --- MARKET SCHEDULE (HIBER-NATION) ---
MARKET_OPEN_HOUR = 4  # 4:00 AM ET (Pre-Market)
MARKET_CLOSE_HOUR = 20 # 8:00 PM ET (After-Hours Close)

import zoneinfo

def get_et_now():
    """Returns current time in ET"""
    tz = zoneinfo.ZoneInfo("America/New_York")
    return datetime.datetime.now(tz).replace(tzinfo=None)

def is_market_open():
    """
    Checks if we are in active system hours (04:00 - 20:00 ET, Mon-Fri).
    Sunday Futures Open (18:00+) is also considered active.
    """
    now = get_et_now()
    
    # 1. Check Weekend
    # Saturday (5): SLEEP ALL DAY
    if now.weekday() == 5: 
        return False
        
    # Sunday (6): SLEEP until 6 PM (Futures Open)
    if now.weekday() == 6:
        if now.hour >= 18: return True
        return False
        
    # Weekdays (0-4): Check Hours
    if MARKET_OPEN_HOUR <= now.hour < MARKET_CLOSE_HOUR:
        return True
        
    return False

def wait_for_market_open():
    """
    Blocking call that sleeps until the market opens.
    Used by scripts to hibernate during off-hours.
    """
    import time
    if is_market_open(): return
    
    print(f"💤 HIBERNATE MODE: Market Closed (ET: {get_et_now().strftime('%H:%M')}). Sleeping...")
    
    while not is_market_open():
        # Sleep in 5-minute chunks to remain responsive (ctrl+c)
        time.sleep(300) 
        
    print(f"🔔 WAKE UP: Market Open (ET: {get_et_now().strftime('%H:%M')})")

ORATS_API_KEY = os.environ.get("ORATS_API_KEY", "YOUR_ORATS_API_KEY")
YOUR_ACCOUNT_ID = TS_ACCOUNT_ID
