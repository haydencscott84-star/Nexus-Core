import datetime
import unittest
from unittest.mock import MagicMock, patch
import nexus_config

class TestSleepMode(unittest.TestCase):
    @patch('nexus_config.datetime')
    def test_sleep_mode_times(self, mock_datetime):
        # Helper to mock time
        def set_mock_time(hour):
            # Create a mock datetime object that behaves like datetime.datetime.now()
            mock_now = MagicMock()
            mock_now.hour = hour
            mock_datetime.datetime.now.return_value = mock_now
            # Also handle utcnow fallback if pytz fails (though we expect pytz to work or fail gracefully)
            mock_datetime.datetime.utcnow.return_value = mock_now 

        # Test Cases
        # 1. Trading Day (10 AM) -> Should be False
        set_mock_time(10)
        self.assertFalse(nexus_config.is_sleep_mode(), "10 AM should NOT be sleep mode")

        # 2. Trading Day (2 PM) -> Should be False
        set_mock_time(14)
        self.assertFalse(nexus_config.is_sleep_mode(), "2 PM should NOT be sleep mode")

        # 3. Market Close (4 PM) -> Should be False (Wait until 7pm)
        set_mock_time(16)
        self.assertFalse(nexus_config.is_sleep_mode(), "4 PM should NOT be sleep mode")

        # 4. Evening (7 PM) -> Should be True
        set_mock_time(19)
        self.assertTrue(nexus_config.is_sleep_mode(), "7 PM SHOULD be sleep mode")

        # 5. Late Night (11 PM) -> Should be True
        set_mock_time(23)
        self.assertTrue(nexus_config.is_sleep_mode(), "11 PM SHOULD be sleep mode")

        # 6. Early Morning (4 AM) -> Should be True
        set_mock_time(4)
        self.assertTrue(nexus_config.is_sleep_mode(), "4 AM SHOULD be sleep mode")

        # 7. Pre-Market (5 AM) -> Should be False (Wake up)
        set_mock_time(5)
        self.assertFalse(nexus_config.is_sleep_mode(), "5 AM should NOT be sleep mode")

        print("✅ All Sleep Mode Logic Tests Passed")

if __name__ == '__main__':
    # Manually run the test case
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSleepMode)
    unittest.TextTestRunner(verbosity=2).run(suite)
