import sys
sys.path.append("/root")
from orats_connector import get_live_chain
import time

print("Testing ORATS Fetch...")
start = time.time()
df = get_live_chain("SPY")
elapsed = time.time() - start

if not df.empty:
    print(f"SUCCESS. Loaded {len(df)} rows in {elapsed:.2f}s.")
    print(df[['expiry', 'strike', 'delta', 'gamma']].head())
else:
    print("FAILURE. DataFrame is empty.")
