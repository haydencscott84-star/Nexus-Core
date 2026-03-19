import sys
import os
import json
from unittest.mock import MagicMock
from nexus_copycat_bot import CopycatDashboard

# Mock Config
LOG_FILE_PATHS = ["logs/test_read_start.log"]

def test_read_from_start():
    print("🚀 Testing Shadow Bot Read-From-Start...")
    
    # 1. Pre-populate Log File (Simulate Backfill)
    os.makedirs("logs", exist_ok=True)
    with open(LOG_FILE_PATHS[0], "w") as f:
        trade = {"ticker": "SPY", "premium": 2_000_000, "expiration": "2025-12-20", "strike": 550, "type": "C", "volume": 1000, "open_interest": 500}
        f.write(json.dumps(trade) + "\n")
        
    # 2. Setup Mock App
    app = CopycatDashboard()
    app.query_one = MagicMock()
    mock_log = MagicMock()
    app.query_one.return_value = mock_log
    
    # Patch paths
    import nexus_copycat_bot
    nexus_copycat_bot.LOG_FILE_PATHS = LOG_FILE_PATHS
    
    # 3. Run poll_logs (Should read the existing line)
    app.poll_logs()
    
    # 4. Verify
    # Check if _total_lines_scanned > 0
    if app._total_lines_scanned > 0:
        print(f"   ✅ Successfully read {app._total_lines_scanned} existing lines.")
    else:
        print(f"   ❌ Failed. Total Lines: {app._total_lines_scanned}")
        sys.exit(1)
        
    # Check logs for "Opened ... (Reading from start...)"
    calls = mock_log.write.call_args_list
    logs = [c[0][0] for c in calls]
    if any("Reading from start" in l for l in logs):
        print("   ✅ Logged 'Reading from start'.")
    else:
        print("   ⚠️ Missing 'Reading from start' log.")

if __name__ == "__main__":
    test_read_from_start()
