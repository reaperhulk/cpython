"""Stress the one-shot LINE/BRANCH path for profiling with perf.

Repeatedly re-enables local LINE (+BRANCH) events on a large function and
executes it, so nearly all time is spent in the fire-once-then-DISABLE
machinery.

Usage:
    perf record -g -- ./python Tools/coverage_benchmark/profile_oneshot.py [line|branch|setup] [reps]
"""

import sys
import time

monitoring = sys.monitoring
E = monitoring.events
TOOL = monitoring.COVERAGE_ID


def make_branchy_function(n_branches):
    lines = ["def branchy(flip):", "    total = 0"]
    for i in range(n_branches):
        lines.append(f"    if (flip + {i}) % 2:")
        lines.append(f"        total += {i}")
        lines.append("    else:")
        lines.append("        total -= 1")
    lines.append("    return total")
    ns = {}
    exec(compile("\n".join(lines) + "\n", "<branchy>", "exec"), ns)
    return ns["branchy"]


def noop_disable(*args):
    return monitoring.DISABLE


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "branch"
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    fn = make_branchy_function(2000)
    fn(0)
    fn(1)

    monitoring.use_tool_id(TOOL, "profile")
    monitoring.register_callback(TOOL, E.LINE, noop_disable)
    monitoring.register_callback(TOOL, E.BRANCH_LEFT, noop_disable)
    monitoring.register_callback(TOOL, E.BRANCH_RIGHT, noop_disable)

    if kind == "line":
        events = E.LINE
    elif kind == "branch":
        events = E.LINE | E.BRANCH_LEFT | E.BRANCH_RIGHT
    elif kind == "setup":
        events = E.LINE | E.BRANCH_LEFT | E.BRANCH_RIGHT
    else:
        raise SystemExit(f"unknown kind {kind}")

    code = fn.__code__
    t0 = time.perf_counter()
    for _ in range(reps):
        monitoring.set_local_events(TOOL, code, 0)
        monitoring.set_local_events(TOOL, code, events)
        if kind != "setup":
            fn(0)
            fn(1)
    t1 = time.perf_counter()
    monitoring.set_events(TOOL, 0)
    monitoring.free_tool_id(TOOL)
    print(f"{kind}: {reps} reps in {t1 - t0:.3f}s")


if __name__ == "__main__":
    main()
