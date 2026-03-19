import zmq
import zmq.asyncio
import asyncio
import json
import requests
import datetime
import sys
import os

# --- CONFIGURATION ---
try:
    from nexus_config import DISCORD_WEBHOOK_URL, ZMQ_PORT_NOTIFICATIONS
except ImportError:
    print("CRITICAL: nexus_config.py not found or missing specific vars.")
    sys.exit(1)

COLOR_MAP = {
    "RED": 0xFF0000,
    "GREEN": 0x00FF00,
    "YELLOW": 0xFFFF00,
    "BLUE": 0x3498DB,
    "ORANGE": 0xFFA500,
    "PURPLE": 0x9B59B6,
    "DARK_RED": 0x8B0000,
    "CYAN": 0x00FFFF
}

class NotificationService:
    def __init__(self):
        self.ctx = zmq.asyncio.Context()
        self.socket = self.ctx.socket(zmq.PULL)
        self.socket.bind(f"tcp://*:{ZMQ_PORT_NOTIFICATIONS}")
        print(f"📡 Notification Service Listening on Port {ZMQ_PORT_NOTIFICATIONS}")
        
        # Test Webhook Connection
        self.webhook_active = False
        if DISCORD_WEBHOOK_URL and "YOUR_WEBHOOK" not in DISCORD_WEBHOOK_URL:
            self.webhook_active = True
            print("✅ Discord Webhook Configured")
        else:
            print("⚠️ Discord Webhook MISSING or INVALID. Messages will only be logged.")
            
        # STATEFUL TRACKING (Topic -> MessageID)
        self.topic_map = {}

    async def run(self):
        print("🟢 Service Started. Waiting for events...")
        while True:
            try:
                # 1. Receive Event
                msg_bytes = await self.socket.recv()
                msg = json.loads(msg_bytes.decode('utf-8'))
                
                # 2. Log Locally
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                title = msg.get("title", "Notification")
                print(f"[{timestamp}] Received: {title} (Topic: {msg.get('topic')})")
                
                # 3. Dispatch to Discord
                if self.webhook_active:
                    await self.send_discord(msg)
                    
            except Exception as e:
                print(f"❌ Receiver Error: {e}")

    async def send_discord(self, msg):
        """
        Constructs and sends/edits the Discord Payload.
        """
        try:
            # Extract fields
            title = msg.get("title", "Nexus Alert")
            desc = msg.get("message", "No content provided.")
            color_key = msg.get("color", "BLUE")
            color_int = COLOR_MAP.get(color_key, COLOR_MAP["BLUE"])
            topic = msg.get("topic") # NEW: Stateful Topic ID
            
            if isinstance(color_key, int): color_int = color_key

            embed = {
                "title": title,
                "description": desc,
                "color": color_int,
                "timestamp": datetime.datetime.now().isoformat(),
                "footer": {"text": "Nexus Notification Service v1.1"}
            }
            if msg.get("fields"): embed["fields"] = msg["fields"]

            payload = {"embeds": [embed]}
            
            # LOGIC: EDIT vs POST
            method = requests.post
            url = f"{DISCORD_WEBHOOK_URL}?wait=true" # Wait to get ID back
            
            # Check if we have a known ID for this topic
            last_id = self.topic_map.get(topic) if topic else None
            
            if last_id:
                # Attempt to PATCH (Edit)
                url = f"{DISCORD_WEBHOOK_URL}/messages/{last_id}"
                method = requests.patch
                print(f"📝 Editing Message {last_id} for Topic {topic}...")

            # EXECUTE
            resp = await asyncio.to_thread(method, url, json=payload)
            
            # HANDLING RESPONSES
            if resp.status_code in [200, 204]:
                if method == requests.post:
                    # New Message - Save ID if topic exists
                    try:
                        new_id = resp.json().get("id")
                        if topic and new_id:
                            self.topic_map[topic] = new_id
                            print(f"📌 Registered Topic '{topic}' -> {new_id}")
                    except: pass
                else:
                    print("✅ Edit Successful")
                    
            elif resp.status_code == 404 and last_id:
                # Message deleted? Retry as new POST
                print(f"⚠️ Message {last_id} missing (404). Sending new one...")
                del self.topic_map[topic]
                await self.send_discord({**msg, "force_new": True})

            elif resp.status_code >= 500:
                # Server Error on Edit? Force New Message to break loop
                print(f"⚠️ Discord Server Error ({resp.status_code}). Clearing State for '{topic}'. SKIPPING RETRY.")
                if topic in self.topic_map:
                    del self.topic_map[topic]
                # [FIX] Do NOT retry immediately. Let the next cycle handle it as a fresh message.
                # Loop breaking precaution.
                
            else:
                print(f"⚠️ Discord API {resp.status_code}: {resp.text}")

        except Exception as e:
            print(f"⚠️ Discord Request Failed: {e}")

if __name__ == "__main__":
    print("🚀 Notification Service v1.2 (Patch 500 Fix) Starting...")
    service = NotificationService()
    try:
        asyncio.run(service.run())
    except KeyboardInterrupt:
        print("🛑 Service Stopping...")
