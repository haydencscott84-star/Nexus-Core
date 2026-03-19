import re

def parse_occ_symbol(symbol):
    print(f"Testing: '{symbol}'")
    try:
        clean_sym = symbol.replace(" ", "")
        # Current Regex (Strict 8 digit strike)
        match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", clean_sym)
        if not match:
            print("❌ Strict Regex Failed")
            
            # Proposed Relaxed Regex
            match_relaxed = re.match(r"^([A-Z]+)(\d{6})([CP])(\d+)$", clean_sym)
            if match_relaxed:
                 print(f"✅ Relaxed Regex Matched: {match_relaxed.groups()}")
            else:
                 print("❌ Relaxed Regex Failed too")
            return None
            
        print("✅ Strict Regex Matched")
        return "OK"
    except Exception as e:
        print(f"Error: {e}")

parse_occ_symbol("SPY 260116P710")
