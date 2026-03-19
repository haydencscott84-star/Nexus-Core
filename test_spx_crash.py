import subprocess
import time

p = subprocess.Popen(["python3", "spx_profiler_nexus.py"])
time.sleep(10)
p.kill()
