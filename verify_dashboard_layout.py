import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

# Add script dir to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock dependencies
sys.modules['nexus_lock'] = MagicMock()
sys.modules['zmq'] = MagicMock()
sys.modules['zmq.asyncio'] = MagicMock()

from trader_dashboard import TraderDashboardV2
from textual.widgets import DataTable

async def verify_layout():
    print("--- VERIFYING DASHBOARD LAYOUT ---")
    
    # Define Test App subclass
    class TestApp(TraderDashboardV2):
        async def on_mount(self):
            print(">> App Mounted")
            try:
                # Call original on_mount to ensure columns are added
                await super().on_mount()
                
                t_pos = self.query_one("#tbl-pos", DataTable)
                t_ord = self.query_one("#tbl-ord", DataTable)
                
                print("✅ PASS: Both Tables Found")
                
                # Check Columns
                cols_pos = [str(c.label) for c in t_pos.columns.values()]
                cols_ord = [str(c.label) for c in t_ord.columns.values()]
                
                print(f"Positions Cols: {cols_pos}")
                print(f"Orders Cols: {cols_ord}")
                
                if "CONTRACT" in cols_pos and "SYMBOL" in cols_ord:
                    print("✅ PASS: Columns Initialized")
                else:
                    print("❌ FAIL: Columns Missing")
                
                self.exit(0)
            except Exception as e:
                print(f"❌ FAIL: Widget Error: {e}")
                self.exit(1)

        # Mock on_ready to prevent network calls
        async def on_ready(self):
            pass

    print(">> Starting Test App...")
    app = TestApp()
    
    # Safety Timer
    async def killer():
        await asyncio.sleep(5)
        print("TIMEOUT: Force Exit")
        app.exit(1)
        
    app.run_worker(killer)
    await app.run_async(headless=True)

if __name__ == "__main__":
    asyncio.run(verify_layout())
