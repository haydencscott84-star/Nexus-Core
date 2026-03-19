import zmq
import json
import time

def verify():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://127.0.0.1:5555")
    socket.subscribe(b"SPY")
    
    print("Listening for SPY on 5555...")
    
    start = time.time()
    while time.time() - start < 10:
        try:
            if socket.poll(1000):
                msg = socket.recv_multipart()
                print(f"RX: {msg}")
            else:
                print(".", end="", flush=True)
        except KeyboardInterrupt:
            break
            
if __name__ == "__main__":
    verify()
