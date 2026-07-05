"""sys.monitoring coverage benchmark harness.

Runs each (workload, mode) combination in fresh subprocesses, several
times, and reports:

  warm    -- min over runs of (import + first rep): includes code-object
             instrumentation, PY_START decisions, per-line first hits and
             the DISABLE/de-instrument path.
  steady  -- min over runs of mean(reps[1:]): residual overhead after
             coverage has disabled everything it is going to disable.

Overheads are reported relative to the "none" mode of the same workload.

Usage:
  ./python Tools/sysmon_bench/harness.py --label mylabel
  ./python Tools/sysmon_bench/harness.py --workloads hotloop,calls --modes none,replica_line
"""

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "runner.py")

DEFAULT_WORKLOADS = [
    "richards",
    "deltablue",
    "nqueens",
    "codegen",
    "hotloop",
    "calls",
    "generators",
    "pygments_hl",
]
DEFAULT_MODES = [
    "none",
    "replica_line",
    "replica_branch",
    "minimal_line",
    "line_nodisable",
    "branch_nodisable",
    "settrace",
]

# Modes whose per-event cost makes hot micro workloads pathologically
# slow; trim reps there so the suite finishes in reasonable time.
SLOW_MODES = {"line_nodisable", "branch_nodisable", "settrace"}


def run_one(python, workload, mode, reps, cpu):
    cmd = []
    if cpu is not None and shutil.which("taskset"):
        cmd += ["taskset", "-c", str(cpu)]
    cmd += [python, "-X", "pycache_prefix=" + os.path.join(HERE, ".pycache"),
            RUNNER, workload, mode, str(reps)]
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if proc.returncode != 0:
        raise RuntimeError(
            f"runner failed for {workload}/{mode}:\n{proc.stdout}\n{proc.stderr}"
        )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def fmt_ms(ns):
    return f"{ns / 1e6:8.2f}"


def fmt_ratio(x):
    return f"{x:7.2f}x"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--workloads", default=",".join(DEFAULT_WORKLOADS))
    ap.add_argument("--modes", default=",".join(DEFAULT_MODES))
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--reps", type=int, default=4)
    ap.add_argument("--cpu", type=int, default=0, help="CPU to pin to (-1 to disable)")
    ap.add_argument("--label", default="unlabeled")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    workloads = args.workloads.split(",")
    modes = args.modes.split(",")
    cpu = None if args.cpu < 0 else args.cpu

    # Throwaway pass to populate the pycache prefix so no measured run
    # pays one-time bytecode compilation.
    for workload in workloads:
        run_one(args.python, workload, "none", 1, cpu)

    results = {}
    for workload in workloads:
        for mode in modes:
            reps = args.reps
            if mode in SLOW_MODES and workload in ("hotloop", "calls", "generators"):
                reps = 2
            runs = []
            for _ in range(args.runs):
                runs.append(run_one(args.python, workload, mode, reps, cpu))
            warm = min(r["import_ns"] + r["times_ns"][0] for r in runs)
            steadies = [
                statistics.mean(r["times_ns"][1:]) for r in runs if len(r["times_ns"]) > 1
            ]
            steady = min(steadies) if steadies else None
            results[(workload, mode)] = {
                "warm_ns": warm,
                "steady_ns": steady,
                "runs": runs,
            }
            s = f"{steady / 1e6:9.2f}ms" if steady is not None else "        -"
            print(
                f"{workload:14s} {mode:17s} warm {warm / 1e6:9.2f}ms  steady {s}",
                flush=True,
            )

    # Summary table
    print()
    print(f"## Results: {args.label}")
    print()
    print(
        "| workload | mode | warm (ms) | warm overhead | steady (ms) | steady overhead |"
    )
    print("|---|---|---:|---:|---:|---:|")
    for workload in workloads:
        base = results.get((workload, "none"))
        for mode in modes:
            r = results[(workload, mode)]
            warm_ov = (
                fmt_ratio(r["warm_ns"] / base["warm_ns"]) if base else "-"
            )
            if r["steady_ns"] is not None and base and base["steady_ns"]:
                steady_ov = fmt_ratio(r["steady_ns"] / base["steady_ns"])
                steady_ms = fmt_ms(r["steady_ns"])
            else:
                steady_ov = "-"
                steady_ms = "-"
            print(
                f"| {workload} | {mode} | {fmt_ms(r['warm_ns'])} | {warm_ov} "
                f"| {steady_ms} | {steady_ov} |"
            )

    out = args.out or os.path.join(HERE, "results", f"{args.label}.json")
    payload = {
        "label": args.label,
        "python": args.python,
        "runs": args.runs,
        "reps": args.reps,
        "results": {
            f"{w}/{m}": {
                "warm_ns": v["warm_ns"],
                "steady_ns": v["steady_ns"],
                "tool_summary": v["runs"][0]["tool_summary"],
            }
            for (w, m), v in results.items()
        },
    }
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
