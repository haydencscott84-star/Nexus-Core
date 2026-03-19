import asyncio
import json
import time
from unittest.mock import MagicMock, AsyncMock
import sys
import os

# Add local scripts to path
sys.path.append(os.getcwd())

try:
    from uw_nexus import UWNexus
except ImportError as e:
    print(f"Could not import UWNexus: {e}")
    sys.exit(1)

async def test_logic():
    print("[*] Initializing UWNexus for testing...")
    app = UWNexus()
    
    # Mock the ZMQ socket
    mock_socket = AsyncMock()
    app.pub_socket = mock_socket
    
    # Mock the log_msg to print to stdout
    app.log_msg = lambda m: print(f"[LOG] {m}")
    
    # 1. Feed some "normal" data to build history (mean/std)
    print("[*] Feeding normal data...")
    import random
    for _ in range(20):
        # Vary premium slightly around 100k
        prem = 100_000.0 + random.uniform(-10000, 10000)
        normal_trade = {
            "ticker": "SPX",
            "total_premium": prem,
            "executed_at": time.time()
        }
        payload = json.dumps(["flow-alerts", normal_trade])
        await app.handle_message(payload)
        
    # 2. Feed a "Whale" trade (High Z-Score)
    print("[*] Feeding WHALE trade...")
    whale_trade = {
        "ticker": "SPX",
        "total_premium": 50_000_000.0, # Huge premium
        "executed_at": time.time()
    }
    payload = json.dumps(["flow-alerts", whale_trade])
    await app.handle_message(payload)
    
    # 3. Check if ALERT was sent
    print("[*] Checking for ALERT broadcast...")
    alert_sent = False
    for call in mock_socket.send_multipart.call_args_list:
        args = call[0][0] # The list [topic, message]
        topic = args[0]
        message = args[1]
        
        if topic == b"system-alerts":
            data = json.loads(message)
            if data['type'] == "ALERT" and data['z_score'] > 4.0:
                print(f"[SUCCESS] Alert Sent! Z-Score: {data['z_score']:.2f}")
                alert_sent = True
                break
    
    if not alert_sent:
        print("[FAIL] No alert was sent.")
    else:
        print("[PASS] Logic verification successful.")

if __name__ == "__main__":
    asyncio.run(test_logic())
