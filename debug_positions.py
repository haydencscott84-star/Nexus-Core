
import zmq
import json
import time

ZMQ_PORT_EXEC = 5567

def debug_positions():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect(f"tcp://127.0.0.1:{ZMQ_PORT_EXEC}")
    
    # Payload
    payload = {"cmd": "GET_POSITIONS", "account": "SIM_ACC"}
    print(f"Sending: {payload}")
    
    sock.send_json(payload)
    
    if sock.poll(5000):
        reply = sock.recv_json()
        status = reply.get("status")
        data = reply.get("data", [])
        
        print(f"Status: {status}")
        print(f"Raw Positions Count: {len(data)}")
        
        print("\n--- RAW DATA ---")
        for p in data:
            print(p)
            
        print("\n--- FILTER SIMULATION (DEBIT vs CREDIT) ---")
        # Logic from nexus_debit.py
        # Spreads only (paired) - simplified check since we might receive flat list or grouped
        # Assuming Data is list of positions. Finding spreads requires grouping.
        # Wait, usually GET_POSITIONS return grouped spreads if 'managed_spreads' logic is used?
        # Or standard list? Standard TS_NEXUS returns a flat list usually.
        # But 'nexus_debit.py' requests 'GET_POSITIONS', let's see how it parses.
        
        # Parse Logic found in nexus_debit.py:
        # It iterates 'active_positions' which usually comes from 'GET_MANAGED_SPREADS'?
        # No, commonly just iterates raw positions and tries to group?
        
        # Let's just see the raw data first.
        pass
        
    else:
        print("Timeout.")

if __name__ == "__main__":
    debug_positions()
