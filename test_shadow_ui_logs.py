import sys
import os
import time
import json
from unittest.mock import MagicMock
from nexus_copycat_bot import CopycatDashboard

# Mock Config
LOG_FILE_PATHS = ["logs/test_ui_logs.log"]

def test_ui_logging():
    print("🚀 Testing Shadow Bot UI Logging...")
    
    # 1. Setup Mock App
    app = CopycatDashboard()
    app.query_one = MagicMock()
    mock_log = MagicMock()
    app.query_one.return_value = mock_log
    
    # 2. Setup Mock Log File
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE_PATHS[0], "w") as f:
        f.write("")
        
    # 3. Run poll_logs (First run inits handles)
    # We need to monkeypatch LOG_FILE_PATHS in the module or instance
    # Since it's a global in the module, we need to patch it there.
    import nexus_copycat_bot
    nexus_copycat_bot.LOG_FILE_PATHS = LOG_FILE_PATHS
    
    app.poll_logs() 
    
    # 4. Write a "Near Miss" trade ($1M)
    trade = {"ticker": "SPY", "premium": 1_000_000, "expiration": "2025-12-20", "strike": 550, "type": "C", "volume": 1000, "open_interest": 500}
    with open(LOG_FILE_PATHS[0], "a") as f:
        f.write(json.dumps(trade) + "\n")
        
    # 5. Run poll_logs again
    app.poll_logs()
    
    # 6. Verify Log Calls
    # We expect:
    # - Heartbeat (maybe, depending on time)
    # - "Seen: SPY $1.0M"
    
    calls = mock_log.write.call_args_list
    logs = [c[0][0] for c in calls]
    print(f"   -> Captured Logs: {logs}")
    
    found_seen = any("Seen: SPY $1.0M" in l for l in logs)
    
    if found_seen:
        print("   ✅ 'Near Miss' Logged successfully.")
    else:
        print("   ❌ Failed to log 'Near Miss'.")
        sys.exit(1)
        
    # Test Heartbeat (Force time forward if needed, or just check logic)
    # The heartbeat logic uses time.time(), so we can't easily force it without mocking time.
    # But checking the Near Miss is sufficient to prove the logging path works.

if __name__ == "__main__":
    test_ui_logging()
