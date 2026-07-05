"""Run a sysmon_bench workload under real coverage.py; print steady-rep time.

Used to compare stock vs patched coverage.py (see coverage-sysmon.patch)
under `coverage run --source=workloads`, e.g.:

  PYTHONPATH=third_party/pylibs COVERAGE_CORE=sysmon \
      python -m coverage run --source=workloads covrun_bench.py calls

Prints JSON with the minimum steady-state rep time (first rep is warmup
and excluded).
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

name = sys.argv[1]
mod = __import__(f"workloads.{name}", fromlist=["x"])
if hasattr(mod, "setup"):
    mod.setup()
mod.run()  # warm/first-hit
times = []
for _ in range(4):
    t0 = time.perf_counter_ns()
    mod.run()
    times.append(time.perf_counter_ns() - t0)
print(json.dumps({"workload": name, "steady_ns": min(times)}))
