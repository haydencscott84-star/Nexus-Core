import os
import requests
# Hardcoded from prompt to verify exact URL
WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "YOUR_WEBHOOK_URL")

def test_send():
    print(f"Testing Webhook: {WEBHOOK[:30]}...")
    payload = {
        "content": "✅ **Antigravity Alert System Configured.**\nStanding by for Market Hours (09:30-16:00 ET) to begin Delta/Gamma reporting."
    }
    try:
        r = requests.post(WEBHOOK, json=payload)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_send()
