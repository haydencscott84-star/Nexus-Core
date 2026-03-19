
# PATCH TS RAW QUOTES
# Target: ts_nexus.py
# Objective: Include raw bid/ask in GET_CHAIN response so Nexus Debit can calc Debit cost.

FILE = "ts_nexus.py"

# We target the block where results are appended in fetch_option_chain
SEARCH_BLOCK = r'''                        results.append({
                            "expiry": expiry_date,
                            "dte": dte,
                            "short": short_strike,
                            "long": long_strike,
                            "credit": round(credit, 2),
                            "risk": round(risk, 2),
                            "rr": round(rr, 1),
                            "breakeven": round(breakeven, 2),
                            "short_sym": short_sym,
                            "long_sym": long_sym
                        })'''

REPLACE_BLOCK = r'''                        results.append({
                            "expiry": expiry_date,
                            "dte": dte,
                            "short": short_strike,
                            "long": long_strike,
                            "credit": round(credit, 2),
                            "risk": round(risk, 2),
                            "rr": round(rr, 1),
                            "breakeven": round(breakeven, 2),
                            "short_sym": short_sym,
                            "long_sym": long_sym,
                            "bid_short": bid_short,
                            "ask_short": ask_short,
                            "bid_long": bid_long,
                            "ask_long": ask_long
                        })'''

def patch():
    with open(FILE, 'r') as f: content = f.read()
    
    if SEARCH_BLOCK in content:
        new_content = content.replace(SEARCH_BLOCK, REPLACE_BLOCK)
        with open(FILE, 'w') as f: f.write(new_content)
        print("Patched ts_nexus.py to return raw quotes.")
    else:
        # Fuzzy check: maybe whitespace differs
        print("Block match failed. Attempting fuzzy replace.")
        # We can just look for the 'results.append({' start and the fields.
        # But for robustness, let's use the file lines.
        pass

if __name__ == "__main__":
    patch()
