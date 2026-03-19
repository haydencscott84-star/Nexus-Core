from textual.app import App, ComposeResult
from textual.widgets import DataTable

class CrashTestApp(App):
    def compose(self) -> ComposeResult:
        yield DataTable()

    def on_mount(self):
        dt = self.query_one(DataTable)
        try:
            print("Attempting to add column with justify='right'...")
            dt.add_column("Test", justify="right")
            print("SUCCESS: justify='right' is supported.")
        except TypeError as e:
            print(f"CRASH REPRODUCED: {e}")
        except Exception as e:
            print(f"OTHER ERROR: {e}")
            
        self.exit()

if __name__ == "__main__":
    app = CrashTestApp()
    app.run()
