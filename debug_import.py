import sys
import os

print(f"CWD: {os.getcwd()}")
print(f"Python: {sys.executable}")
print(f"Path: {sys.path}")

print("\n--- Listing Files ---")
print(os.listdir("."))

print("\n--- Attempting Imports ---")
try:
    import nexus_config
    print("✅ nexus_config imported")
except Exception as e:
    print(f"❌ nexus_config failed: {e}")

try:
    import tradestation_explorer
    print("✅ tradestation_explorer imported")
except Exception as e:
    print(f"❌ tradestation_explorer failed: {e}")

try:
    import pandas_ta
    print("✅ pandas_ta imported")
except Exception as e:
    print(f"❌ pandas_ta failed: {e}")

try:
    import textual
    print("✅ textual imported")
except Exception as e:
    print(f"❌ textual failed: {e}")
