import asyncio
import zmq.asyncio

# CONFIG (Must match ts_nexus.py)
PORT = 5567 

async def ping_nexus():
    ctx = zmq.asyncio.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(f"tcp://127.0.0.1:{PORT}")
    
    print(f"--- ATTEMPTING CONNECT TO PORT {PORT} ---")
    
    # 1. Send a dummy command
    payload = {"cmd": "GET_OPEN_ORDERS"} # Safe command that expects a reply
    print(f"Sending: {payload}")
    await sock.send_json(payload)
    
    # 2. Wait for reply with a strict timeout
    print("Waiting for reply...")
    if await sock.poll(timeout=3000): # 3 second timeout
        reply = await sock.recv_json()
        print(f"SUCCESS! Nexus Replied: {reply}")
    else:
        print("FAILURE: Connection Timed Out. Nexus is not listening or is hung.")

if __name__ == "__main__":
    asyncio.run(ping_nexus())