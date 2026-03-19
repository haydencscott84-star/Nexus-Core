import re

# Test strings from the screenshot (approximate)
# Label: AUTO (260130P672/260130P667)
# This implies short_sym.split(' ')[-1] is 260130P672
symbols = [
    "SPY 260130P672",
    "SPY 260220C705",
    "SPX 241219C5800", # Example standard
    "SPY 260130P667"
]

regex = r'([CP])0*(\d+(?:\.\d+)?)$'

print(f"Testing regex: {regex}")
for s in symbols:
    short_sym = s
    try:
        match = re.search(regex, short_sym)
        if match:
            bg = match.groups()
            k = float(bg[1])
            print(f"MATCH: {s} -> Type: {bg[0]}, Strike: {k}")
        else:
            print(f"FAIL: {s}")
    except Exception as e:
        print(f"ERROR: {s} -> {e}")
