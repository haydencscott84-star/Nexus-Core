
import asyncio
import json
import unittest.mock
from unittest.mock import MagicMock
import sys

# Mock requests before importing ts_nexus to avoid ImportErrors or network calls
sys.modules['requests'] = MagicMock()
sys.modules['zmq'] = MagicMock()
sys.modules['zmq.asyncio'] = MagicMock()

# Import the patched module
import ts_nexus

async def simulate_order():
    print("--- SIMULATING TRADESTATION ORDER ---")
    
    # Instantiate Engine (mocking init to skip networking)
    engine = ts_nexus.NexusEngine()
    engine.TS = MagicMock()
    engine.TS._get_valid_access_token.return_value = "MOCK_TOKEN"
    engine.TS.BASE_URL = "https://api.tradestation.com/v3"
    
    # Mock requests.post to capture payload
    with unittest.mock.patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Orders": [{"OrderID": "SIMULATED_12345"}]}
        mock_post.return_value = mock_response
        
        # Test Case 1: Short Format (The Buggy Case)
        # "SPY 600C" -> Should be Option
        # "SPY 250116C600" -> Should be Option with Correct Symbol
        
        symbol_input = "SPY 250116C600" 
        print(f"\n[TEST] Input Symbol: {symbol_input}")
        
        await engine.execute_order(symbol_input, 1, "MARKET", "BUY")
        
        # Extract arguments from mock call
        args, kwargs = mock_post.call_args
        payload = kwargs.get('json', {})
        
        print("\n[TRADESTATION PAYLOAD]")
        print(json.dumps(payload, indent=2))
        
        asset_type = payload.get("AssetType")
        actual_symbol = payload.get("Symbol")
        
        if asset_type == "Option" and actual_symbol == "SPY 250116C600":
            print("\n✅ SUCCESS: Payload correctly identified as OPTION with valid symbol.")
        else:
            print(f"\n❌ FAILURE: AssetType={asset_type}, Symbol={actual_symbol}")

if __name__ == "__main__":
    asyncio.run(simulate_order())
