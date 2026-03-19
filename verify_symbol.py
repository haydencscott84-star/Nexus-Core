
import requests
import json
import logging
import sys
import os

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Import TS Manager
try:
    from tradestation_explorer import TradeStationManager
    from nexus_config import TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID
except ImportError as e:
    logging.error(f"Import Error: {e}")
    sys.exit(1)

def main():
    logging.info("Starting Symbol Verification...")
    
    # Initialize TS Manager
    ts = TradeStationManager(TS_CLIENT_ID, TS_CLIENT_SECRET, TS_ACCOUNT_ID)
    
    # List of candidate symbols to test
    candidates = [
        "MESH26",       # User provided
        "MESH26",       # Standard TS Future
        "@MES",         # Continuous Contract
        "MES26",        # Short year
        "MESH6",        # Single digit year
        "MESH2026",     # Long year
        "MES",          # Root
        "@MESH26"       # With @
    ]
    
    logging.info(f"Testing {len(candidates)} candidates: {candidates}")
    
    found_valid = []
    
    for sym in candidates:
        try:
            quote = ts.get_quote_snapshot(sym)
            if quote:
                last_price = quote.get("Last")
                logging.info(f"✅ VALID: {sym} | Last: {last_price} | Desc: {quote.get('Description')}")
                found_valid.append(sym)
            else:
                logging.warning(f"❌ INVALID: {sym}")
        except Exception as e:
            logging.error(f"Error testing {sym}: {e}")
            
    if found_valid:
        print("\n\n--- VALID SYMBOLS FOUND ---")
        for s in found_valid:
            print(f"  -> {s}")
    else:
        print("\n\n--- NO VALID SYMBOLS FOUND ---")

if __name__ == "__main__":
    main()
