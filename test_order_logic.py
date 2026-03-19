
import re
import json

def test_execute_order(symbol):
    print(f"--- Testing Symbol: '{symbol}' ---")
    
    asset_type = "Stock"
    
    # 1. Detect OCC Format (ROOT + YYMMDD + C/P + STRIKE) e.g. SPY251231C00699000
    # TS requires Space + Short Strike: SPY 251231C699
    occ_match = re.match(r"^([A-Z]+)(\d{6}[CP])(\d+)$", symbol.replace(" ", ""))
    
    final_symbol = symbol
    
    if occ_match:
        print(" [MATCH] Regex Matched")
        root = occ_match.group(1)
        expiry_type = occ_match.group(2)
        strike_raw = occ_match.group(3)
        
        # Convert Strike: 00699000 -> 699
        try:
            # FIXED LOGIC
            strike_val = float(strike_raw)
            if len(strike_raw) >= 8: # Standard OCC is 8 digits padded
                 strike_val = strike_val / 1000.0

            if strike_val.is_integer():
                strike_str = str(int(strike_val))
            else:
                strike_str = str(strike_val)
            
            final_symbol = f"{root} {expiry_type}{strike_str}"
            asset_type = "Option"
        except:
            if " " not in symbol: final_symbol = f"{root} {expiry_type}{strike_raw}"
            asset_type = "Option"
            
    elif " " in symbol or len(symbol) > 8: 
        print(" [MATCH] Space/Len Check")
        asset_type = "Option"
    else:
        print(" [FAIL] No Match -> Stock")

    print(f" RESULT: AssetType={asset_type}, Symbol='{final_symbol}'")
    return asset_type, final_symbol

# Test Cases
test_execute_order("SPY") # Expected: Stock, SPY
test_execute_order("SPY 600C") # Expected: Option (via space check). Symbol remains "SPY 600C". Valid for TS? No.
test_execute_order("SPY250116C00600000") # Expected: Option, SPY 250116C600. Correct.
test_execute_order("SPY 250116C600") # Expected: Option. Parsing issue?
# "SPY 250116C600" -> replace space -> "SPY250116C600"
# Match ^([A-Z]+)(\d{6}[CP])(\d+)$ -> Group 3 is "600".
# 600 / 1000 = 0.6.
# Result: "SPY 250116C0". WRONG.
