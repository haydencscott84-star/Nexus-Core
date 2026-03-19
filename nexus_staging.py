# FILE: nexus_staging.py
"""
NEXUS STAGING MANAGER
- Views all "Queued/Open" orders directly from TradeStation API.
- Allows "Select & Kill" management.
"""
import sys, asyncio, json, datetime
import zmq, zmq.asyncio
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer, Button, Static, Label
from textual.containers import Container, Horizontal, Vertical
from rich.text import Text

# CONFIG
ZMQ_PORT_EXEC = 5567
LOCAL_IP = "127.0.0.1"

class NexusStaging(App):
    CSS = """
    Screen { background: #0F111A; }
    #header { height: 3; dock: top; background: #2E3440; border-bottom: solid #88C0D0; content-align: center middle; }
    DataTable { height: 1fr; border: solid #4C566A; }
    #controls { height: 5; dock: bottom; background: #2E3440; padding: 1; }
    Button { width: 100%; height: 3; }
    #btn-refresh { background: #4C566A; color: white; }
    #btn-cancel { background: #BF616A; color: white; }
    """

    zmq_ctx = zmq.asyncio.Context()
    selected_order_id = None

    def compose(self) -> ComposeResult:
        yield Static("NEXUS ORDER STAGING", id="header")
        yield DataTable(id="order_table")
        with Horizontal(id="controls"):
            with Container(classes="col"): yield Button("REFRESH (Manual)", id="btn-refresh")
            with Container(classes="col"): yield Button("CANCEL SELECTED", id="btn-cancel", disabled=True)
        yield Footer()

    async def on_mount(self):
        self.ex = self.zmq_ctx.socket(zmq.REQ)
        self.ex.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
        dt = self.query_one(DataTable)
        dt.cursor_type = "row"
        dt.add_columns("ID", "Symbol", "Side", "Qty", "Type", "Price", "Status", "Time")
        self.set_interval(3.0, self.fetch_orders)
        self.fetch_orders()

    async def fetch_orders(self):
        try:
            await self.ex.send_json({"cmd": "GET_OPEN_ORDERS"})
            if await self.ex.poll(2000):
                resp = await self.ex.recv_json()
                if resp.get("status") == "ok": self.update_table(resp.get("orders", []))
                else: self.notify(f"Error: {resp.get('msg')}", severity="error")
            else:
                self.notify("Timeout: Nexus Backend Offline?", severity="warning")
                self.ex.close(); self.ex = self.zmq_ctx.socket(zmq.REQ); self.ex.connect(f"tcp://{LOCAL_IP}:{ZMQ_PORT_EXEC}")
        except Exception as e: self.notify(f"Connection Error: {e}", severity="error")

    def update_table(self, orders):
        dt = self.query_one(DataTable)
        active_ids = []
        for o in orders:
            oid = str(o.get("OrderID"))
            active_ids.append(oid)
            sym = o.get("Symbol", "???"); side = o.get("BuyOrSell", "?")
            qty = str(o.get("QuantityOrdered", 0)); typ = o.get("OrderType", "MKT")
            px = o.get("LimitPrice", "MKT"); stat = o.get("Status", "???")
            time = o.get("OpenedDateTime", "")[11:19]
            stat_styled = Text(stat)
            if stat == "Open": stat_styled.stylize("bold green")
            elif stat == "Queued": stat_styled.stylize("bold yellow")
            if oid not in [str(k) for k in dt.rows]: dt.add_row(oid, sym, side, qty, typ, px, stat_styled, time, key=oid)
        
        for r_key in list(dt.rows.keys()):
            if r_key not in active_ids: dt.remove_row(r_key)
        
        if self.selected_order_id and self.selected_order_id not in active_ids:
            self.selected_order_id = None; self.query_one("#btn-cancel").disabled = True

    def on_data_table_row_selected(self, event):
        self.selected_order_id = event.row_key.value; self.query_one("#btn-cancel").disabled = False

    async def on_button_pressed(self, event):
        if event.button.id == "btn-refresh": await self.fetch_orders()
        elif event.button.id == "btn-cancel":
            if self.selected_order_id: await self.cancel_order(self.selected_order_id)

    async def cancel_order(self, oid):
        self.notify(f"Cancelling {oid}...")
        try:
            await self.ex.send_json({"cmd": "CANCEL_ORDER", "order_id": oid})
            resp = await self.ex.recv_json()
            if resp.get("status") == "ok": self.notify("Order Cancelled", severity="information"); await self.fetch_orders()
            else: self.notify(f"Cancel Failed: {resp.get('msg')}", severity="error")
        except: self.notify("Cancel Error", severity="error")

if __name__ == "__main__": NexusStaging().run()