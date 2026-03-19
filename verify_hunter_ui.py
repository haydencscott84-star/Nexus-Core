import sys
import os
from nexus_hunter import NexusHunter

class TestHunter(NexusHunter):
    async def on_mount(self):
        print("TEST: App Mounted. Starting Timer...")
        await super().on_mount()
        
        # Verify Log Window Exists
        try:
            log = self.query_one("#log_win")
            print("✅ RichLog Widget Found.")
        except:
            print("❌ RichLog Widget MISSING.")
            self.exit(1)
            
        # Schedule exit after 3 seconds
        self.set_timer(3.0, self.exit_test)

    def exit_test(self):
        print("TEST: Timer Expired. Exiting...")
        self.exit(0)

if __name__ == "__main__":
    print("--- Verifying Nexus Hunter UI Runtime (Main Thread) ---")
    try:
        app = TestHunter()
        app.run()
        print("✅ App Ran and Exited Successfully.")
    except Exception as e:
        print(f"❌ App Crashed: {e}")
        sys.exit(1)
