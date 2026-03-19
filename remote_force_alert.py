import zmq
import json
import requests
import sys
import os

# --- PATH HACK ---
sys.path.append(os.getcwd())
try:
    from nexus_config import DISCORD_WEBHOOK_URL, ZMQ_PORT_NOTIFICATIONS
except ImportError:
    print("❌ Config Missing!")
    sys.exit(1)

print("-- DIAGNOSIS START --")

# 1. DIRECT WEBHOOK TEST
print(f"1. Testing Direct Webhook: {DISCORD_WEBHOOK_URL[:30]}...")
try:
    payload = {"content": "🚨 **NEXUS SYSTEM TEST**: This is a direct verification alert requested by user."}
    r = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if r.status_code in [200, 204]:
        print("✅ Direct Webhook SUCCESS")
    else:
        print(f"❌ Direct Webhook FAILED: {r.status_code} {r.text}")
except Exception as e:
    print(f"❌ Direct Webhook EXCEPTION: {e}")

# 2. ZMQ PIPELINE TEST
print(f"\n2. Testing ZMQ Pipeline (Port {ZMQ_PORT_NOTIFICATIONS})...")
try:
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.connect(f"tcp://localhost:{ZMQ_PORT_NOTIFICATIONS}")
    
    msg = {
        "title": "📡 ZMQ Pipeline Test",
        "message": "This message proves the internal notification bus is active.",
        "color": 3447003, # Blue
        "topic": "TEST_TOPIC"
    }
    sock.send_json(msg, flags=zmq.NOBLOCK)
    print("✅ ZMQ Message Sent. Check Discord to see if it moves from Service -> Webhook.")
except Exception as e:
    print(f"❌ ZMQ Test FAILED: {e}")

print("-- DIAGNOSIS END --")
