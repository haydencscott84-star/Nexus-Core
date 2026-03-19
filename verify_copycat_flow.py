import zmq
import time
import subprocess
import sys
import json

print("🧪 Starting Copycat Verification...")

# 1. Start Listener (Simulating Dashboard)
ctx = zmq.Context()
sock = ctx.socket(zmq.SUB)
sock.connect("tcp://127.0.0.1:5563")
sock.subscribe(b"SELECT_SHADOW")
print("🎧 Listening on 5563 for Shadow Signals...")

# 2. Start Bot in Sim Mode
print("🚀 Launching Bot...")
with open("bot_debug.log", "w") as f:
    proc = subprocess.Popen(["python3", "nexus_copycat_bot.py", "--sim"], stdout=f, stderr=f)

# 3. Wait for Signal
try:
    if sock.poll(timeout=20000): # 20s timeout
        msg = sock.recv_multipart()
        topic = msg[0].decode()
        payload = json.loads(msg[1].decode())
        print(f"✅ RECEIVED SIGNAL!")
        print(f"   Topic: {topic}")
        print(f"   Payload: {payload}")
        print("🎉 VERIFICATION SUCCESSFUL: Bot -> ZMQ -> Dashboard Path is Open.")
    else:
        print("❌ TIMEOUT: No signal received from Bot.")
        # Print bot output for debug
        try:
            out, err = proc.communicate(timeout=5)
            print("Bot Output:\n", out.decode())
            print("Bot Error:\n", err.decode())
        except Exception as e:
            print(f"Could not capture output: {e}")

except Exception as e:
    print(f"❌ ERROR: {e}")

finally:
    proc.terminate()
    print("🛑 Test Complete.")
