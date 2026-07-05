"""Run one (workload, mode) combination in this process and print JSON.

Usage: python runner.py WORKLOAD MODE REPS

The monitoring tool is started before the workload module is imported so
module-level code is traced, like real coverage runs.  The first rep
("warm") includes import plus all first-hit instrumentation costs;
later reps measure steady state.
"""

import gc
import importlib
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import covtools


def main():
    workload_name, mode, reps = sys.argv[1], sys.argv[2], int(sys.argv[3])

    tool = covtools.TOOLS[mode]()

    # Import the workload package machinery *before* monitoring starts,
    # so that what we measure under monitoring is dominated by the
    # workload itself (plus its own imports).
    importlib.import_module("workloads")

    gc.collect()
    tool.start()

    t0 = time.perf_counter_ns()
    workload = importlib.import_module(f"workloads.{workload_name}")
    if hasattr(workload, "setup"):
        workload.setup()
    import_ns = time.perf_counter_ns() - t0

    times = []
    checksum = None
    for _ in range(reps):
        t0 = time.perf_counter_ns()
        checksum = workload.run()
        times.append(time.perf_counter_ns() - t0)

    tool.stop()

    print(
        json.dumps(
            {
                "workload": workload_name,
                "mode": mode,
                "reps": reps,
                "import_ns": import_ns,
                "times_ns": times,
                "checksum": checksum,
                "tool_summary": tool.summary(),
            }
        )
    )


if __name__ == "__main__":
    main()
