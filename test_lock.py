import nexus_lock
import time
import sys

print(f"PID {sys.argv[1]}: Attempting to acquire lock...")
nexus_lock.enforce_singleton()
print(f"PID {sys.argv[1]}: Lock acquired! Sleeping for 5s...")
time.sleep(5)
print(f"PID {sys.argv[1]}: Exiting.")
