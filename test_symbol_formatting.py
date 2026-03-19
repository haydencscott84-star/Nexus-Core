
import re

def format_ts_symbol(symbol):
    # Regex for OCC: Root (chars), Date (6 digits), Type (C/P), Strike (8 digits)
    # Examples: SPY251219C00680000, IWM251219P00412500
    occ_match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", symbol)
    
    if occ_match:
        root = occ_match.group(1)
        date = occ_match.group(2)
        otype = occ_match.group(3)
        raw_strike = occ_match.group(4)
        
        # Convert Strike
        strike_val = int(raw_strike) / 1000.0
        
        # Format Strike: remove trailing .0 if integer
        if strike_val == int(strike_val):
            strike_str = str(int(strike_val))
        else:
            strike_str = str(strike_val)
            
        return f"{root} {date}{otype}{strike_str}"
    
    # Fallback to simple space insertion if partial match (robustness)
    # e.g. if strike isn't exactly 8 chars?
    return symbol

tests = [
    "SPY251219C00680000", # Standard Int
    "SPY251219P00412500", # Standard Decimal
    "IWM251219C00200000", # Standard Int
    "SPY",               # Stock
    "SPY 251219C680",    # Already Formatted
]

print("--- TESTING SYMBOL FORMAT ---")
for t in tests:
    print(f"Original: {t}  ->  Formatted: {format_ts_symbol(t)}")
