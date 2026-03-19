import sys, os
import zmq
try:
    import nexus_config
    print(f"CONFIG LOADED. MARKET PORT: {nexus_config.ZMQ_PORT_MARKET}")
except ImportError:
    print("CONFIG IMPORT FAILED")
    sys.exit(1)

print(f"ATTEMPTING TO BIND {nexus_config.ZMQ_PORT_MARKET}...")
ctx = zmq.Context()
sock = ctx.socket(zmq.PUB)
try:
    sock.bind(f"tcp://*:{nexus_config.ZMQ_PORT_MARKET}")
    print("BIND SUCCESS!")
    sock.close()
except Exception as e:
    print(f"BIND FAILED: {e}")
