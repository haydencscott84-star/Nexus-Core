import zmq
import json
import time
from rich.console import Console

console = Console()
ZMQ_PORT = 9998 # Test Port to avoid conflict with Main Feed (9999)

def trigger_fire_drill():
    context = zmq.Context()
    socket = context.socket(zmq.PUB)
    socket.bind(f"tcp://*:{ZMQ_PORT}")
    
    # Give time for subscribers to connect (if we were binding)
    # BUT alert_manager binds SUB? No, alert_manager connects SUB to PUB.
    # Wait, alert_manager says: socket.connect(f"tcp://localhost:{ZMQ_PORT}")
    # So alert_manager is the SUBSCRIBER connecting to a PUBLISHER.
    # So THIS script must be the PUBLISHER and BIND.
    # Correct.
    
    console.print(f"[bold yellow]🔥 INITIATING FIRE DRILL on Port {ZMQ_PORT}...[/]")
    console.print("[dim]Waiting 2s for Alert Manager to pick up connection...[/]")
    time.sleep(2)
    
    # Mock Data: Price $695.00 (Triggers Yellow Warning & Red Stop Loss)
    # We inject 'sim_4h_close' to force the Candle Alert.
    payload = {
        "type": "SIMULATION",
        "ticker": "SPY",
        "underlying_price": 695.00, # Triggers > 682.50
        "sim_4h_close": 695.00,     # Triggers > 689.00
        "timestamp": time.time()
    }
    
    topic = "SPY"
    socket.send_multipart([topic.encode(), json.dumps(payload).encode('utf-8')])
    
    console.print(f"[bold green]🚀 PAYLOAD SENT:[/]\n{json.dumps(payload, indent=2)}")
    console.print("\n[bold white]Check your Discord Channel NOW.[/]")
    console.print("[dim]You should see:\n1. ⚠️ TACTICAL WARNING\n2. 🛑 STOP LOSS TRIGGERED[/]")
    
    time.sleep(1) # Ensure message flushes
    socket.close()
    context.term()

if __name__ == "__main__":
    trigger_fire_drill()
