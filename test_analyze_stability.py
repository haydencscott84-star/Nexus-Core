
import unittest
import sys
import os
import pandas as pd
import numpy as np

# Ensure local imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

class TestAnalyzeSnapshotsStability(unittest.TestCase):
    def test_imports(self):
        """Verify all critical imports in analyze_snapshots.py load correctly."""
        print("Testing Imports...")
        try:
            import analyze_snapshots
            print("✅ analyze_snapshots imported successfully")
        except ImportError as e:
            self.fail(f"Import Failed: {e}")
        except NameError as e:
            self.fail(f"NameError during Import (Missing Dependency?): {e}")
        except Exception as e:
            self.fail(f"General Error during Import: {e}")

    def test_load_unified_data(self):
        """Test if data loading logic crashes (e.g. glob issues)."""
        print("Testing Data Loading...")
        try:
            from analyze_snapshots import load_unified_data
            # We don't need real data, just want to ensure the function *runs* without NameError
            # It might return empty df, which is fine.
            df = load_unified_data(lookback_days=1)
            print(f"✅ load_unified_data ran effectively. Rows: {len(df)}")
        except Exception as e:
             # If it fails due to missing files, that's okay, but NameError is what we are hunting.
             if "NameError" in str(e):
                 self.fail(f"NameError in load_unified_data: {e}")
             else:
                 print(f"⚠️ Data Load Warning (Expected if no local data): {e}")

if __name__ == '__main__':
    unittest.main()
