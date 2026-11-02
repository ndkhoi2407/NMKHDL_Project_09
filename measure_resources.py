import subprocess
import sys
import psutil
import time
import shutil

p = subprocess.Popen(
    [sys.executable, "src/benchmark.py", "--report-only"]
)

proc = psutil.Process(p.pid)
peak = 0
samples = []

disk0 = shutil.disk_usage("data").used
start = time.perf_counter()

while p.poll() is None:
    try:
        rss = proc.memory_info().rss
        peak = max(peak, rss)
        samples.append(rss)
    except psutil.NoSuchProcess:
        break
    time.sleep(0.05)

rc = p.wait()
disk1 = shutil.disk_usage("data").used
runtime = time.perf_counter() - start

print(f"RAM peak: {peak / 1024 / 1024:.2f} MB")
print(f"RAM avg: {sum(samples) / len(samples) / 1024 / 1024:.2f} MB")
print(f"Disk data: {disk1 / 1024 / 1024:.2f} MB")
print(f"Disk change: {(disk1 - disk0) / 1024 / 1024:.2f} MB")
print(f"Runtime report-only: {runtime:.2f}s")
print(f"Return code: {rc}")
