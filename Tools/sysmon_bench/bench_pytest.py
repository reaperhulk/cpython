"""Benchmark coverage overhead on a real pytest suite (pyca/cryptography).

Setup (once):
    ./python Tools/sysmon_bench/fetch_cryptography.py

Then:
    ./python Tools/sysmon_bench/bench_pytest.py --python ./python --runs 3

Configs compare wall-clock time of the same pytest invocation:
  none            -- plain pytest
  cov_sysmon      -- coverage.py (stock, pip-installed), COVERAGE_CORE=sysmon
  cov_ctrace      -- coverage.py (stock), COVERAGE_CORE=ctrace (C tracer)
  cov_sysmon_patched -- coverage.py from third_party/coverage-patched
                     (local-events + lazy byte_to_line fixes), sysmon core

Each config runs in a fresh subprocess, pinned with taskset, and reports
the pytest exit status, number of tests, and wall time.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
THIRD_PARTY = os.path.join(HERE, "third_party")


def find_crypto_root():
    for d in sorted(os.listdir(THIRD_PARTY)):
        if d.startswith("cryptography-") and os.path.isdir(
            os.path.join(THIRD_PARTY, d, "tests")
        ):
            return os.path.join(THIRD_PARTY, d)
    raise RuntimeError("run fetch_cryptography.py first")


CONFIGS = ["none", "cov_sysmon", "cov_ctrace", "cov_sysmon_patched"]


def run_one(python, config, tests, cpu, keep_data=False):
    root = find_crypto_root()
    pylibs = os.path.join(THIRD_PARTY, "pylibs")
    patched = os.path.join(THIRD_PARTY, "coverage-patched")

    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    pypath = [pylibs]
    if config == "cov_sysmon_patched":
        pypath.insert(0, patched)
    env["PYTHONPATH"] = os.pathsep.join(pypath)

    cmd = []
    if cpu is not None and shutil.which("taskset"):
        cmd += ["taskset", "-c", str(cpu)]
    cmd += [os.path.abspath(python)]

    pytest_args = [
        "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line",
        # cryptography's addopts require pytest-benchmark; neutralize them.
        "-o", "addopts=",
    ] + tests

    if config == "none":
        cmd += pytest_args
    else:
        env["COVERAGE_CORE"] = "ctrace" if config == "cov_ctrace" else "sysmon"
        env["COVERAGE_FILE"] = os.path.join(THIRD_PARTY, f".coverage.{config}")
        cmd += [
            "-m", "coverage", "run", "--source=cryptography",
        ] + pytest_args

    t0 = time.perf_counter_ns()
    proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
    elapsed = time.perf_counter_ns() - t0

    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    m = re.search(r"(\d+) passed", tail)
    npassed = int(m.group(1)) if m else None
    if proc.returncode not in (0,):
        sys.stderr.write(f"[{config}] rc={proc.returncode}\n{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}\n")
    if not keep_data and config != "none":
        try:
            os.unlink(env["COVERAGE_FILE"])
        except FileNotFoundError:
            pass
    return {
        "config": config,
        "elapsed_ns": elapsed,
        "returncode": proc.returncode,
        "passed": npassed,
        "summary_line": tail,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument(
        "--tests",
        default="tests/x509",
        help="space-separated pytest targets relative to the cryptography root",
    )
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--cpu", type=int, default=0)
    ap.add_argument("--label", default="pytest-crypto")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cpu = None if args.cpu < 0 else args.cpu
    tests = args.tests.split()
    results = {}
    for config in args.configs.split(","):
        runs = [run_one(args.python, config, tests, cpu) for _ in range(args.runs)]
        best = min(r["elapsed_ns"] for r in runs)
        results[config] = {"best_ns": best, "runs": runs}
        print(
            f"{config:20s} best {best / 1e9:7.2f}s  "
            f"passed={runs[0]['passed']} rc={runs[0]['returncode']}",
            flush=True,
        )

    base = results.get("none")
    print()
    for config, r in results.items():
        ratio = r["best_ns"] / base["best_ns"] if base else float("nan")
        print(f"{config:20s} {r['best_ns'] / 1e9:7.2f}s  {ratio:5.2f}x")

    out = args.out or os.path.join(HERE, "results", f"{args.label}.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"label": args.label, "python": args.python, "results": results}, f, indent=1)
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
