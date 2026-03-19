import re
val_str = "$6710 [SPY $669.23] [+$3.8B \u0394]"

m_spy = re.search(r'SPY\s*\$?([0-9,]+(?:\.[0-9]+)?)', val_str)
if m_spy:
    print(f"SPY price: {m_spy.group(1)}")

m = re.search(r'\$?([0-9,]+(?:\.[0-9]+)?)', val_str)
if m:
    print(f"Main price: {m.group(1)}")

