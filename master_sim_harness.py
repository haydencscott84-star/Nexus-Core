import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np
import json
import os
import sys

# Import System Components
import watchtower_engine
import gemini_market_auditor

class MasterSimulationHarness(unittest.TestCase):
    
    def setUp(self):
        print("\n⚡ [SIMULATION] Initializing Harness...")
        self.mock_market_data = self.create_crash_scenario()
        
    def create_crash_scenario(self):
        print("⚡ [SIMULATION] Injecting Scenario: FLASH CRASH (VIX=40, Inverted)")
        dates = pd.date_range(end=pd.Timestamp.now(), periods=100)
        data = {
            "SPY": np.linspace(500, 450, 100), # Crashing
            "RSP": np.linspace(160, 140, 100),
            "^VIX": np.full(100, 40.0), # Panic
            "^VIX3M": np.full(100, 35.0), # Inverted (Spot > 3M)
            "^VVIX": np.full(100, 150.0)
        }
        return pd.DataFrame(data, index=dates)

    @patch('watchtower_engine.fetch_data')
    @patch('gemini_market_auditor.send_discord_msg')
    def test_full_pipeline(self, mock_discord, mock_fetch):
        # 1. SETUP MOCKS
        mock_fetch.return_value = self.mock_market_data
        
        # Mock Gemini Response (We don't care what it says, we care what it HEARS)
        mock_chat = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "I acknowledge the Red Light. HEDGING."
        mock_chat.send_message.return_value = mock_response
        
        # Mock the GLOBAL model instance in the module
        mock_model_instance = MagicMock()
        mock_model_instance.generate_content.return_value = mock_response
        
        # CRITICAL FIX: Replace the global 'model' variable
        original_model = gemini_market_auditor.model
        gemini_market_auditor.model = mock_model_instance

        # 2. RUN WATCHTOWER (The Eyes)
        print("⚡ [SIMULATION] Running Watchtower Engine...")
        watchtower_engine.run_watchtower()
        
        # Verify Watchtower Output
        with open("market_state_live.json", "r") as f:
            state = json.load(f)
        
        print(f"   Watchtower Output: {state['alert_level']} | {state['regime']}")
        self.assertEqual(state['alert_level'], "RED", "Watchtower failed to trigger RED light on VIX=40")
        self.assertTrue(state['consensus_votes']['term_structure_inverted'], "Watchtower failed to detect Inversion")

        # 3. RUN AUDITOR (The Mind)
        print("⚡ [SIMULATION] Running Gemini Auditor...")
        auditor = gemini_market_auditor.MarketAuditor()
        
        # We need to mock the 'market_state.json' read inside run_cycle too?
        # Actually, run_cycle reads 'market_state.json' (Bridge) AND 'market_state_live.json' (Watchtower).
        # We just wrote the real 'market_state_live.json' in step 2.
        # But 'market_state.json' might be missing or stale. 
        # Let's create a dummy 'market_state.json' to prevent errors.
        dummy_bridge = {
            "market_structure": {"trend_5d": "BEARISH"},
            "spy_flow": {"net_gex": -1000000},
            "system_status": "ONLINE"
        }
        with open("market_state.json", "w") as f:
            json.dump(dummy_bridge, f)

        # Run Cycle
        try:
            auditor.run_cycle()
        except Exception as e:
            print(f"   Auditor Crashed: {e}")
            # It might crash if other files are missing, but let's see.
        
        # 4. INTERCEPT PROMPT (The Interceptor)
        # Check what was sent to generate_content
        call_args = mock_model_instance.generate_content.call_args
        if call_args:
            prompt_sent = call_args[0][0]
            print("\n⚡ [SIMULATION] Intercepted Prompt sent to Gemini:")
            # print(prompt_sent[:500] + "...") # Print snippet
            
            # 5. ASSERTIONS (The Proof)
            print("   Checking for 'PROHIBITED' instruction...")
            self.assertIn("PROHIBITED from recommending Long entries", prompt_sent)
            
            print("   Checking for 'CRITICAL RISK' warning...")
            self.assertIn("CRITICAL RISK", prompt_sent)
            
            print("   Checking for 'Alert Level: RED'...")
            self.assertIn("Alert Level: RED", prompt_sent)
            
            print("✅ PASS: System correctly escalated Panic Data -> Red Light -> Prohibitive Prompt.")
        else:
            self.fail("❌ FAIL: Gemini was never called.")

if __name__ == '__main__':
    unittest.main()
