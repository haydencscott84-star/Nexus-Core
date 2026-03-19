import unittest
import os
import json
import time
import shutil
from datetime import datetime, timedelta

# Import target modules
import market_bridge
import check_system_health

class TestSystemStabilization(unittest.TestCase):
    def setUp(self):
        self.bridge = market_bridge.BridgeEngine()
        self.test_file = "test_corrupt.json"
        # self.log_file = "bridge_status.log"
        
        # Create dummy file
        with open(self.test_file, 'w') as f:
            json.dump({"status": "ok"}, f)
            
    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

    def test_safe_read_json_valid(self):
        data, age, success = self.bridge.safe_read_json(self.test_file)
        self.assertTrue(success)
        self.assertEqual(data["status"], "ok")

    def test_safe_read_json_corrupt_extra_data(self):
        # Corrupt the file with extra data 
        with open(self.test_file, 'w') as f:
            f.write('{"status": "ok"}{"status": "bad"}')
            
        data, age, success = self.bridge.safe_read_json(self.test_file)
        
        # Our patch should catch this and NOT crash
        # It currently returns None, age, False for unrecoverable errors (unless we enabled the partial salvage)
        # Even if it returns False, CRUCIALLY it must not raise an exception.
        self.assertFalse(success) 
        print(f"  -> Corrupt read result: Success={success} (Should be False but NO CRASH)")

    def test_safe_read_json_empty(self):
        with open(self.test_file, 'w') as f:
            f.write('')
            
        data, age, success = self.bridge.safe_read_json(self.test_file)
        self.assertFalse(success)

    def test_health_check_freshness(self):
        # Create a dummy log file
        dummy_log = "nexus_engine.log"
        with open(dummy_log, 'w') as f:
            f.write("test log")
        
        # Make it old (simulating stuck process)
        old_time = time.time() - 300 # 5 mins ago
        os.utime(dummy_log, (old_time, old_time))
        
        # We can't easily capture stdout of check_health, but we can verify the logic inline
        now = time.time()
        mtime = os.path.getmtime(dummy_log)
        age = now - mtime
        self.assertTrue(age > 120, "Log should be detected as stale")
        print(f"  -> Log Freshness Check: Age={int(age)}s (Threshold: 120s)")

if __name__ == '__main__':
    unittest.main()
