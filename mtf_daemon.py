import asyncio
import sys
import os
import signal
import datetime
from unittest.mock import MagicMock

# 1. Mock Textual to allow import without TTY
# We need to mock it BEFORE importing mtf_nexus
try:
    import textual.app
    import textual.widgets
except ImportError:
    # If textual not installed or fails, we mock it completely
    sys.modules['textual.app'] = MagicMock()
    sys.modules['textual.widgets'] = MagicMock()
    sys.modules['textual.containers'] = MagicMock()
    sys.modules['rich.text'] = MagicMock()

# 2. Mock App Base for mtf_nexus import
# Since mtf_nexus.py imports App from textual.app, we need to ensure it doesn't crash
if 'textual.app' in sys.modules:
    sys.modules['textual.app'].App = MagicMock

# 3. Import Target
import mtf_nexus

# 4. Define Headless Runner
class HeadlessMTF:
    def __init__(self):
        self.app = mtf_nexus.MTFNexusApp()
        
        # Patch UI methods to be No-Op or Loggers
        self.app.query_one = lambda *args: MagicMock() 
        self.app.log_msg = self.log_msg
        self.app.run_worker = self.fake_worker
        self.app.set_interval = lambda *args: None # We handle loop
        
        # Initialize
        print("🚀 MTF Headless Daemon Started")
        self.running = True
        
        # Startup Flag
        self.app.is_startup = True

    def log_msg(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}")
        sys.stdout.flush()

    async def fake_worker(self, awaitable, exclusive=False):
        await awaitable

    async def run_loop(self):
        # Initial run
        print("🔄 Startup Analysis...")
        await self.app.async_analysis()
        
        while self.running:
            # 15 Minute Interval (900s)
            print("💤 Sleeping 15 minutes...")
            await asyncio.sleep(900)
            print("⏰ Waking up for Analysis...")
            try:
                await self.app.async_analysis()
            except Exception as e:
                print(f"❌ Loop Error: {e}")

    async def start(self):
        await self.run_loop()

if __name__ == "__main__":
    daemon = HeadlessMTF()
    try:
        asyncio.run(daemon.start())
    except KeyboardInterrupt:
        print("🛑 Daemon Stopped")
