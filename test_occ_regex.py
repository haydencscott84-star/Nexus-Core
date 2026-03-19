import re
import datetime

def parse_occ_symbol(symbol):
    print(f"Testing Symbol: '{symbol}'")
    try:
        clean_sym = symbol.replace(" ", "")
        print(f"Cleaned: '{clean_sym}'")
        match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", clean_sym)
        if not match:
            print("❌ No Match")
            return "SPY", None, "C", 0.0
            
        ticker = match.group(1)
        date_str = match.group(2) # YYMMDD
        opt_type = match.group(3) # C or P
        strike_str = match.group(4)
        
        expiry = datetime.datetime.strptime(date_str, "%y%m%d").strftime("%Y-%m-%d")
        strike = float(strike_str) / 1000.0
        
        print(f"✅ Match: {ticker} {expiry} {opt_type} {strike}")
        return ticker, expiry, opt_type, strike
    except Exception as e:
        print(f"⚠️ Exception: {e}")
        return "SPY", None, "C", 0.0

# Test Cases
symbols = [
    "SPY 251219C00600000", # Standard
    "SPY251219P00600000",  # No space
    "SPY 251219 P 00600000", # Extra spaces
    "SPXW 251219C05000000", # 4 letter ticker
    "INVALID_SYMBOL"       # Garbage
]

for s in symbols:
    parse_occ_symbol(s)
    print("-" * 20)
