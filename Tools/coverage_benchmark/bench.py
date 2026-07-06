"""Benchmark harness for coverage-style sys.monitoring overhead.

Runs each (workload, mode) pair in fresh subprocesses and reports the
overhead of each coverage mode relative to uninstrumented execution.

Two numbers matter:

* cold  -- first execution of the workload under tracing.  For one-shot
           (DISABLE-based) coverage this includes every per-location event
           exactly once, which is how a real coverage run behaves over a
           test suite.
* steady -- best later in-process iteration, after all one-shot events have
           fired and the bytecode has been de-instrumented.

Usage:
    ./python Tools/coverage_benchmark/bench.py
    ./python Tools/coverage_benchmark/bench.py --modes all --procs 7
    ./python Tools/coverage_benchmark/bench.py --workloads breadth,calls \
        --modes none,shim-branch --json results.json
"""

import argparse
import json
import os
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import workloads
from tracers import ALL_MODES, DEFAULT_MODES


def run_child(python, workload, mode, iters, verbose=False):
    cmd = [
        python,
        os.path.join(HERE, "child.py"),
        "--workload",
        workload,
        "--mode",
        mode,
        "--iters",
        str(iters),
    ]
    env = dict(os.environ)
    env.setdefault("PYTHONHASHSEED", "0")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            f"child failed ({workload}/{mode}):\n{proc.stderr[-2000:]}"
        )
    if verbose and proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return json.loads(proc.stdout.strip().splitlines()[-1])


def measure(python, workload, mode, procs, iters, verbose=False):
    colds = []
    steadies = []
    result = None
    for _ in range(procs):
        result = run_child(python, workload, mode, iters, verbose)
        times = result["times"]
        colds.append(times[0])
        if len(times) > 1:
            steadies.append(min(times[1:]))
    return {
        "workload": workload,
        "mode": mode,
        "cold": min(colds),
        "cold_all": colds,
        "steady": min(steadies) if steadies else None,
        "checksum": result["checksum"],
        "stats": result["stats"],
    }


def pct(value, base):
    return 100.0 * (value - base) / base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--workloads", default="all")
    parser.add_argument("--modes", default="default")
    parser.add_argument("--procs", type=int, default=5,
                        help="fresh processes per (workload, mode)")
    parser.add_argument("--iters", type=int, default=5,
                        help="in-process iterations (first is cold)")
    parser.add_argument("--json", dest="json_out", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.workloads == "all":
        wl_names = list(workloads.WORKLOADS)
    else:
        wl_names = args.workloads.split(",")

    if args.modes == "default":
        modes = list(DEFAULT_MODES)
    elif args.modes == "all":
        modes = list(ALL_MODES)
    else:
        modes = args.modes.split(",")
    if "none" not in modes:
        modes.insert(0, "none")

    all_results = []
    for wl in wl_names:
        base = None
        rows = []
        for mode in modes:
            res = measure(args.python, wl, mode, args.procs, args.iters,
                          args.verbose)
            if mode == "none":
                base = res
            rows.append(res)
            all_results.append(res)
        # print table for this workload
        print(f"\n== {wl} ==")
        header = (f"{'mode':18} {'cold(ms)':>10} {'cold ovh':>9} "
                  f"{'steady(ms)':>11} {'steady ovh':>10} {'points':>8}")
        print(header)
        print("-" * len(header))
        for res in rows:
            cold_ovh = pct(res["cold"], base["cold"])
            if res["steady"] is not None and base["steady"] is not None:
                steady_ms = f"{res['steady'] * 1000:11.1f}"
                steady_ovh = f"{pct(res['steady'], base['steady']):9.1f}%"
            else:
                steady_ms = " " * 11
                steady_ovh = " " * 10
            points = res["stats"].get("points", "")
            print(
                f"{res['mode']:18} {res['cold'] * 1000:10.1f} "
                f"{cold_ovh:8.1f}% {steady_ms} {steady_ovh} {points:>8}"
            )
        sys.stdout.flush()

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(all_results, f, indent=2)
        print(f"\nwrote {args.json_out}")


if __name__ == "__main__":
    main()
