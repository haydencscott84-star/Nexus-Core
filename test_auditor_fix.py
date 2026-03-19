
import sys
import os
import unittest.mock
from unittest.mock import MagicMock

# Mock imports before loading the script to prevent immediate execution or side effects
sys.modules['google.generativeai'] = MagicMock()
sys.modules['requests'] = MagicMock()

# Add script dir
sys.path.append(os.getcwd())

import gemini_market_auditor

# Mock the Model and Discord
gemini_market_auditor.model = MagicMock()
gemini_market_auditor.model.generate_content.return_value.text = '{"action": "HOLD", "reasoning": "Mocked Response"}'
gemini_market_auditor.send_discord_msg = MagicMock()

print("🚀 RUNNING AUDITOR FIX VERIFICATION")

auditor = gemini_market_auditor.MarketAuditor()

# Capture stdout
from io import StringIO
import sys

captured_output = StringIO()
sys.stdout = captured_output

try:
    auditor.run_cycle()
except Exception as e:
    sys.stdout = sys.__stdout__
    print(f"❌ EXECUTION FAILED: {e}")
    sys.exit(1)

sys.stdout = sys.__stdout__
output = captured_output.getvalue()

print("\n🔍 AUDITOR OUTPUT LOG:")
print(output)

print("-" * 50)
if "TICKER: NONE" in output or "TICKER: N/A" in output:
    print("✅ PASS: Auditor correctly identified NO POSITION (Stale Data Fallback worked).")
elif "TICKET: SPY" in output and "260116" in output:
    print("❌ FAIL: Auditor picked up the STALE SPY POSITION.")
else:
    print("⚠️ INDETERMINATE: Check log above.")
