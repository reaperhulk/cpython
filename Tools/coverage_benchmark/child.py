"""Run one (workload, mode) measurement in a fresh process.

Prints a JSON object with per-iteration wall times.  Iteration 1 is the
"cold" run: with one-shot (DISABLE-based) coverage it pays all of the
instrumentation, callback and de-instrumentation costs, exactly like a real
coverage run over fresh code.  Later iterations show the steady state.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import workloads
from tracers import make_tracer


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", required=True)
    parser.add_argument("--mode", required=True)
    parser.add_argument("--iters", type=int, default=5)
    args = parser.parse_args()

    wl = workloads.load(args.workload)
    extra_prefix = wl.setup()

    prefixes = [os.path.join(os.path.dirname(os.path.abspath(__file__)), "workloads")]
    if extra_prefix:
        prefixes.append(extra_prefix)

    tracer = make_tracer(args.mode, prefixes)

    times = []
    checksum = None
    tracer.start()
    try:
        for _ in range(args.iters):
            t0 = time.perf_counter()
            checksum = wl.run()
            t1 = time.perf_counter()
            times.append(t1 - t0)
    finally:
        tracer.stop()
        if hasattr(wl, "teardown"):
            wl.teardown()

    print(
        json.dumps(
            {
                "workload": args.workload,
                "mode": args.mode,
                "times": times,
                "checksum": repr(checksum),
                "stats": tracer.stats(),
            }
        )
    )


if __name__ == "__main__":
    main()
