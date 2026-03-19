import zmq
import json

def test_multi_quote():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.connect("tcp://127.0.0.1:5567")
    
    # Test GET_MANAGED_SPREADS
    print("Testing GET_MANAGED_SPREADS...")
    sock.send_json({"cmd": "GET_MANAGED_SPREADS"})
    if sock.poll(10000):
        reply = sock.recv_json()
        print(f"MANAGED SPREADS: {json.dumps(reply, indent=2)}")
    else:
        print("TIMEOUT GET_MANAGED_SPREADS")

    # Test GET_MULTI_QUOTE
    print("\nTesting GET_MULTI_QUOTE...")
    sock.send_json({"cmd": "GET_MULTI_QUOTE", "symbols": ["SPY 260313P660", "SPY 260313P655"]})
    if sock.poll(10000):
        reply = sock.recv_json()
        print(f"MULTI_QUOTE: {json.dumps(reply, indent=2)}")
    else:
        print("TIMEOUT GET_MULTI_QUOTE")

if __name__ == "__main__":
    test_multi_quote()
