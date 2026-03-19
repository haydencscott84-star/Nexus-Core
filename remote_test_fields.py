import zmq
import json
import sys
import os

sys.path.append(os.getcwd())
try:
    from nexus_config import ZMQ_PORT_NOTIFICATIONS
except ImportError:
    print("❌ Config Missing!")
    sys.exit(1)

print(f"Testing Rich Fields on Port {ZMQ_PORT_NOTIFICATIONS}...")

try:
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUSH)
    sock.connect(f"tcp://localhost:{ZMQ_PORT_NOTIFICATIONS}")
    
    fields = [
        {"name": "🎯 Position", "value": "BULLISH SPY\nEntry: $580.00", "inline": True},
        {"name": "💰 Performance", "value": "P/L: +15.5%\nAcct: +1.2%", "inline": True},
        {"name": "⚡ Greeks", "value": "Delta: 0.45\nGamma: 0.02\nTheta: -0.15", "inline": True}
    ]

    msg = {
        "title": "🧪 FIELD TEST: Auditor Upgrade",
        "message": "This is a verification test for the new detailed field layout.",
        "color": 3447003,
        "topic": "TEST_FIELDS",
        "fields": fields
    }
    
    sock.send_json(msg, flags=zmq.NOBLOCK)
    print("✅ Rich Payload Sent via ZMQ.")
    
except Exception as e:
    print(f"❌ Test Failed: {e}")
