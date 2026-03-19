import os
import requests
import json

# Hardcoded from ENV for testing (assuming standard setup)
# Or read from env vars if possible. 
# I will use the one found in the file if I can see it? 
# The file likely imports it from structure_nexus or environment.
# I'll rely on the one I see in the Auditor file or hardcode if I know it.
# Wait, I don't have the webhook URL. It's likely in `nexus_sheets_bridge.py` or `structure_nexus.py`.
# Let me grep it from `structure_nexus.py` on the remote or local...
# Actually, I'll use the one from `structure_nexus.py` local file.

# Reading from structure_nexus.py local...
# It's usually os.getenv('DISCORD_WEBHOOK_URL').
# I will try to read the local `structure_nexus.py` to see if there's a default, or create a script that imports it.

from structure_nexus import send_discord_msg

if __name__ == "__main__":
    print("Testing Discord...")
    try:
        send_discord_msg("🧪 **Test Message from Auditor Verification**", color=16776960)
        print("✅ Sent")
    except Exception as e:
        print(f"❌ Failed: {e}")
