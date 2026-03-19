from textual.app import App, ComposeResult
from textual.widgets import Label
import asyncio, time
import pandas as pd
from analyze_snapshots import load_unified_data

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield Label("Starting...", id="lbl")

    def on_mount(self):
        self.query_one("#lbl", Label).update("Mounting worker...")
        self.run_worker(self.load_history_background, exclusive=False)

    async def load_history_background(self):
        self.query_one("#lbl", Label).update("Running executor...")
        loop = asyncio.get_event_loop()
        try:
            full_df = await loop.run_in_executor(None, load_unified_data, 5, None)
            self.query_one("#lbl", Label).update(f"Done: {len(full_df)} rows")
        except Exception as e:
            self.query_one("#lbl", Label).update(f"Error: {e}")

if __name__ == "__main__":
    app = TestApp()
    app.run()
